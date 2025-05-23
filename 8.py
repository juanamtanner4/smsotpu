import requests
import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import asyncio
import time
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta
import json
import logging
import os
import pytz
import hashlib

# লগিং সেটআপ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# টেলিগ্রাম বট সেটআপ
BOT_TOKEN = "7735025169:AAGIrr4OlRm0Yv0fIyri6hvsUH-znBtREeo"
CHAT_ID = "-1002639503570"
ADMIN_CHAT_ID = "-1002639503570"
ADMIN_USER_IDS = [849641986]  # অ্যাডমিনদের user_id (যেমন, @Bappyx2)
ADMINS_FILE = "admins.json"
bot = telegram.Bot(token=BOT_TOKEN)

# লগইন এবং এসএমঐস তথ্য
LOGIN_URL = "https://www.ivasms.com/login"
SMS_LIST_URL = "https://www.ivasms.com/portal/sms/received/getsms/number"
SMS_DETAILS_URL = "https://www.ivasms.com/portal/sms/received/getsms/number/sms"
EMAIL = "bappyrb02@gmail.com"
PASSWORD = "bappyrb02@gmail.com"  # সঠিক পাসওয়ার্ড দিন

# এসএমঐস হেডার
SMS_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.ivasms.com/portal/sms/received",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Accept": "text/html, */*; q=0.01",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# নতুন এসএমঐস ট্র্যাক করার জন্য সেট
seen_sms = set()
TIME_THRESHOLD = timedelta(minutes=60)

# ফাইলের নাম
NUMBERS_RANGES_FILE = "numbers_ranges.json"
SEEN_SMS_FILE = "seen_sms.json"

# অপেক্ষার তথ্য
pending_ranges = {}  # {chat_id: {"range": str, "numbers": list}}

# ডিবাগ ফাইলের জন্য ডিরেক্টরি
DEBUG_LOG_DIR = "debug_logs"
if not os.path.exists(DEBUG_LOG_DIR):
    os.makedirs(DEBUG_LOG_DIR)

# অ্যাডমিন পার্সিস্টেন্স
def load_admins():
    """Load admin IDs from admins.json."""
    global ADMIN_USER_IDS
    if os.path.exists(ADMINS_FILE):
        try:
            with open(ADMINS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                ADMIN_USER_IDS = data.get("admin_ids", ADMIN_USER_IDS)
            logger.info(f"লোড করা অ্যাডমিন আইডি: {ADMIN_USER_IDS}")
        except Exception as e:
            logger.error(f"অ্যাডমিন ফাইল লোড করতে ত্রুটি: {e}")
    else:
        logger.info("অ্যাডমিন ফাইল পাওয়া যায়নি, ডিফল্ট অ্যাডমিন ব্যবহার করা হচ্ছে")

def save_admins():
    """Save admin IDs to admins.json."""
    try:
        with open(ADMINS_FILE, "w", encoding="utf-8") as f:
            json.dump({"admin_ids": ADMIN_USER_IDS}, f, ensure_ascii=False, indent=4)
        logger.info("অ্যাডমিন আইডি সংরক্ষণ করা হয়েছে")
    except Exception as e:
        logger.error(f"অ্যাডমিন ফাইল সংরক্ষণে ত্রুটি: {e}")

# Load admins at startup
load_admins()

async def send_startup_alert(chat_id=CHAT_ID):
    """বট স্টার্টআপ অ্যালার্ট পাঠানো"""
    try:
        current_time = datetime.now(pytz.timezone('Asia/Dhaka')).strftime("%d-%m-%Y %H:%M:%S")
        startup_msg = (
            f"✨ *Bot Started* ✨\n\n"
            f"⏰ *Time:* {current_time}\n"
            f"📞 *Status:* Running!\n"
            f"🔧 *Service:* Seven1Tel / Ivasms\n\n"
            f"🔑 *Info:* Ready for OTPs"
        )
        keyboard = [
            [InlineKeyboardButton("Bot Owner", url="https://t.me/Bappyx2")],
            [InlineKeyboardButton("Join Backup", url="https://t.me/ipsharechat")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await bot.send_message(
            chat_id=chat_id,
            text=startup_msg,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        logger.info("স্টার্টআপ অ্যালার্ট পাঠানো হয়েছে")
    except Exception as e:
        logger.error(f"স্টার্টআপ অ্যালার্ট পাঠাতে সমস্যা: {str(e)}")
        await send_telegram_message(f"❌ স্টার্টআপ অ্যালার্ট পাঠাতে সমস্যা: {str(e)}", chat_id)

def initialize_numbers_ranges_file():
    """JSON ফাইল তৈরি করা যদি না থাকে"""
    default_data = {"ranges": []}
    try:
        if not os.path.exists(NUMBERS_RANGES_FILE):
            with open(NUMBERS_RANGES_FILE, "w", encoding="utf-8") as f:
                json.dump(default_data, f, indent=2)
            logger.info(f"JSON ফাইল তৈরি করা হয়েছে: {NUMBERS_RANGES_FILE}")
    except Exception as e:
        logger.error(f"numbers_ranges.json ফাইল তৈরি করতে সমস্যা: {str(e)}")

def initialize_seen_sms_file():
    """seen_sms.json ফাইল তৈরি করা যদি না থাকে"""
    try:
        if not os.path.exists(SEEN_SMS_FILE):
            with open(SEEN_SMS_FILE, "w", encoding="utf-8") as f:
                json.dump({"sms_ids": [], "last_updated": datetime.now().isoformat()}, f)
            logger.info(f"seen_sms ফাইল তৈরি করা হয়েছে: {SEEN_SMS_FILE}")
    except Exception as e:
        logger.error(f"seen_sms ফাইল তৈরি করতে সমস্যা: {str(e)}")

def load_seen_sms():
    """seen_sms.json থেকে দেখা SMS আইডি লোড করা"""
    global seen_sms
    initialize_seen_sms_file()
    try:
        with open(SEEN_SMS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        seen_sms = set(data.get("sms_ids", []))
        logger.info(f"seen_sms.json থেকে {len(seen_sms)}টি SMS আইডি লোড করা হয়েছে")
    except Exception as e:
        logger.error(f"seen_sms.json লোড করতে সমস্যা: {str(e)}")
        seen_sms = set()

def save_seen_sms():
    """seen_sms.json ফাইলে দেখা SMS আইডি সংরক্ষণ করা"""
    try:
        with open(SEEN_SMS_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "sms_ids": list(seen_sms),
                "last_updated": datetime.now().isoformat()
            }, f, indent=2)
        logger.info("seen_sms.json ফাইলে SMS আইডি সংরক্ষণ করা হয়েছে")
    except Exception as e:
        logger.error(f"seen_sms.json সংরক্ষণ করতে সমস্যা: {str(e)}")
        asyncio.create_task(send_telegram_message(f"❌ seen_sms.json সংরক্ষণ করতে সমস্যা: {str(e)}", CHAT_ID))

def load_numbers_ranges():
    """JSON ফাইল থেকে নাম্বার এবং রেঞ্জ লোড করা"""
    initialize_numbers_ranges_file()
    try:
        with open(NUMBERS_RANGES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        numbers = []
        ranges = []
        for range_item in data.get("ranges", []):
            range_value = str(range_item.get("range", "")).strip()
            range_numbers = range_item.get("numbers", [])
            if range_value and range_value not in ranges:
                ranges.append(range_value)
            for num in range_numbers:
                if num not in numbers:
                    numbers.append(str(num))
        logger.info(f"JSON থেকে লোড করা নাম্বার: {numbers}")
        logger.info(f"JSON থেকে লোড করা রেঞ্জ: {ranges}")
        return numbers, ranges
    except Exception as e:
        error_msg = f"❌ JSON ফাইল লোড করতে সমস্যা: {str(e)}"
        logger.error(error_msg)
        asyncio.create_task(send_telegram_message(error_msg, CHAT_ID))
        return [], []

def save_numbers_ranges(ranges_data):
    """JSON ফাইলে নাম্বার এবং রেঞ্জ সংরক্ষণ করা"""
    try:
        if not isinstance(ranges_data, list):
            logger.error(f"Invalid ranges_data type: {type(ranges_data)}")
            raise ValueError("ranges_data must be a list")
        
        cleaned_ranges = []
        for range_item in ranges_data:
            if not isinstance(range_item, dict) or "range" not in range_item or "numbers" not in range_item:
                logger.warning(f"Skipping invalid range item: {range_item}")
                continue
            range_item_copy = range_item.copy()
            range_item_copy["range"] = str(range_item_copy["range"]).strip()
            range_item_copy["numbers"] = [str(num) for num in list(set(range_item.get("numbers", [])))]
            cleaned_ranges.append(range_item_copy)
        
        logger.info(f"Saving ranges to JSON: {cleaned_ranges}")
        with open(NUMBERS_RANGES_FILE, "w", encoding="utf-8") as f:
            json.dump({"ranges": cleaned_ranges}, f, indent=2)
        logger.info("JSON ফাইলে রেঞ্জ এবং নাম্বার সংরক্ষণ করা হয়েছে")
    except Exception as e:
        error_msg = f"❌ JSON ফাইল সংরক্ষণ করতে সমস্যা: {str(e)}"
        logger.error(error_msg)
        asyncio.create_task(send_telegram_message(error_msg, CHAT_ID))

def delete_all_numbers_ranges():
    """সকল নম্বর এবং রেঞ্জ ডিলিট করা"""
    try:
        initialize_numbers_ranges_file()
        with open(NUMBERS_RANGES_FILE, "w", encoding="utf-8") as f:
            json.dump({"ranges": []}, f, indent=2)
        logger.info("সকল নম্বর এবং রেঞ্জ ডিলিট করা হয়েছে")
        return True
    except Exception as e:
        logger.error(f"সকল নম্বর এবং রেঞ্জ ডিলিট করতে সমস্যা: {str(e)}")
        asyncio.create_task(send_telegram_message(f"❌ সকল নম্বর এবং রেঞ্জ ডিলিট করতে সমস্যা: {str(e)}", CHAT_ID))
        return False

def validate_phone_number(number):
    """ফোন নাম্বার বৈধ কি না চেক করা"""
    pattern = r"^\d{8,12}$"
    return bool(re.match(pattern, str(number)))

def mask_phone_number(number):
    """ফোন নম্বরের ৬ষ্ঠ এবং ৭ম ডিজিট মাস্ক করা"""
    logger.info(f"Original number input: '{number}'")
    cleaned_number = ''.join(c for c in str(number) if c.isdigit() or c == '+')
    has_plus = cleaned_number.startswith('+')
    cleaned_number = cleaned_number.lstrip('+')
    logger.info(f"Cleaned number: '{cleaned_number}'")
    
    if len(cleaned_number) >= 8:
        if len(cleaned_number) >= 7:
            masked = f"{cleaned_number[:5]}**{cleaned_number[7:]}"
        else:
            masked = f"{cleaned_number[:5]}**"
        if has_plus:
            masked = f"+{masked}"
        logger.info(f"Masked number: '{masked}'")
        return masked
    elif len(cleaned_number) > 0:
        masked = f"+{cleaned_number}" if has_plus else cleaned_number
        logger.info(f"Number too short, returning: '{masked}'")
        return masked
    else:
        logger.warning("Empty number after cleaning, returning '+Unknown'")
        return "+Unknown"

async def send_telegram_message(message, chat_id=CHAT_ID, reply_markup=None):
    """টেলিগ্রামে মেসেজ পাঠানো"""
    logger.info(f"Sending Telegram message to chat_id {chat_id}: {message[:100]}...")
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=message,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        logger.info(f"টেলিগ্রামে মেসেজ পাঠানো হয়েছে: {message[:100]}...")
    except telegram.error.BadRequest as e:
        logger.error(f"টেলিগ্রাম মেসেজ পাঠাতে সমস্যা (Bad Request): {str(e)}")
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=message,
                reply_markup=reply_markup,
                parse_mode=None
            )
            logger.info(f"টেলিগ্রামে মেসেজ পাঠানো হয়েছে (Markdown ছাড়া): {message[:100]}...")
        except Exception as e2:
            logger.error(f"টেলিগ্রামে মেসেজ পাঠাতে পুনরায় সমস্যা: {str(e2)}")
    except telegram.error.InvalidToken:
        logger.error("টেলিগ্রাম বট টোকেন ভুল। BotFather থেকে টোকেন চেক করুন।")
    except telegram.error.NetworkError as e:
        logger.error(f"টেলিগ্রাম নেটওয়ার্ক সমস্যা: {str(e)}")
    except Exception as e:
        logger.error(f"টেলিগ্রামে মেসেজ পাঠাতে সমস্যা: {str(e)}")

def login_and_get_csrf(max_retries=3):
    """লগইন করে CSRF টোকেন এবং সেশন নেওয়া"""
    for attempt in range(max_retries):
        session = requests.Session()
        try:
            logger.info(f"লগইন চেষ্টা {attempt + 1}/{max_retries}...")
            login_page = session.get(LOGIN_URL, headers=SMS_HEADERS, timeout=10)
            logger.info(f"লগইন পেজের স্ট্যাটাস কোড: {login_page.status_code}")
            soup = BeautifulSoup(login_page.text, 'html.parser')
            csrf_input = soup.find('input', {'name': '_token'})
            if not csrf_input:
                logger.error("CSRF টোকেন পাওয়া যায়নি!")
                return None, None
            csrf_token = csrf_input['value']
            logger.info(f"CSRF টোকেন: {csrf_token}")
            
            payload = {
                "_token": csrf_token,
                "email": EMAIL,
                "password": PASSWORD
            }
            logger.info("লগইন রিকোয়েস্ট পাঠানো হচ্ছে...")
            login_response = session.post(LOGIN_URL, data=payload, headers=SMS_HEADERS, timeout=10)
            logger.info(f"লগইন রেসপন্স স্ট্যাটাস কোড: {login_response.status_code}")
            logger.info(f"সেশন কুকিজ: {session.cookies.get_dict()}")
            if login_response.status_code != 200 or "Dashboard" not in login_response.text:
                error_msg = f"❌ লগইন ব্যর্থ! চেষ্টা {attempt + 1}/{max_retries}"
                logger.error(error_msg)
                asyncio.create_task(send_telegram_message(error_msg, CHAT_ID))
                if attempt < max_retries - 1:
                    time.sleep(5)
                continue
            logger.info("লগইন সফল!")
            return session, csrf_token
        except Exception as e:
            error_msg = f"❌ লগইন করতে সমস্যা (চেষ্টা {attempt + 1}/{max_retries}): {str(e)}"
            logger.error(error_msg)
            asyncio.create_task(send_telegram_message(error_msg, CHAT_ID))
            if attempt < max_retries - 1:
                time.sleep(5)
    return None, None

async def sync_numbers_from_api(session, csrf_token, chat_id=CHAT_ID):
    """API থেকে নাম্বার এবং রেঞ্জ ফেচ করে numbers_ranges.json আপডেট করা"""
    try:
        logger.info("Starting API synchronization for numbers and ranges...")
        
        url = f"https://www.ivasms.com/portal/numbers?draw=2&columns%5B0%5D%5Bdata%5D=number_id&columns%5B0%5D%5Bname%5D=id&columns%5B0%5D%5Borderable%5D=false&columns%5B1%5D%5Bdata%5D=Number&columns%5B2%5D%5Bdata%5D=range&columns%5B3%5D%5Bdata%5D=A2P&columns%5B4%5D%5Bdata%5D=P2P&columns%5B5%5D%5Bdata%5D=action&columns%5B5%5D%5Bsearchable%5D=false&columns%5B5%5D%5Borderable%5D=false&order%5B0%5D%5Bcolumn%5D=1&order%5B0%5D%5Bdir%5D=desc&start=0&length=-1&search%5Bvalue%5D=&_={int(time.time() * 1000)}"
        
        headers = SMS_HEADERS.copy()
        headers.update({
            "x-csrf-token": csrf_token,
            "Accept": "application/json"
        })
        
        response = session.get(url, headers=headers, timeout=10)
        logger.info(f"API response status code: {response.status_code}")
        
        if not response.ok:
            error_msg = f"❌ API sync failed! Status code: {response.status_code}"
            logger.error(error_msg)
            await send_telegram_message(error_msg, chat_id)
            return False
        
        try:
            data = response.json()
            logger.info(f"API response data: {json.dumps(data, indent=2)[:500]}...")
        except ValueError as e:
            error_msg = f"❌ Failed to parse API response as JSON: {str(e)}"
            logger.error(error_msg)
            await send_telegram_message(error_msg, chat_id)
            return False
        
        ranges_data = []
        for record in data.get("data", []):
            range_value = str(record.get("range", "")).strip() if record.get("range") is not None else ""
            number = str(record.get("Number", "")).strip() if record.get("Number") is not None else ""
            if not range_value or not number or not validate_phone_number(number):
                logger.warning(f"Skipping invalid record: range={range_value}, number={number}")
                continue
            existing_range = next((item for item in ranges_data if item["range"] == range_value), None)
            if existing_range:
                if number not in existing_range["numbers"]:
                    existing_range["numbers"].append(number)
            else:
                ranges_data.append({"range": range_value, "numbers": [number]})
        
        try:
            with open(NUMBERS_RANGES_FILE, "r", encoding="utf-8") as f:
                existing_data = json.load(f).get("ranges", [])
        except FileNotFoundError:
            logger.info("No existing numbers_ranges.json found, creating new.")
            existing_data = []
        
        for api_range in ranges_data:
            range_value = api_range["range"]
            numbers = api_range["numbers"]
            existing_range = next((item for item in existing_data if item["range"] == range_value), None)
            if existing_range:
                existing_range["numbers"] = list(set(existing_range["numbers"] + numbers))
            else:
                existing_data.append(api_range)
        
        save_numbers_ranges(existing_data)
        
        total_ranges = len(existing_data)
        total_numbers = sum(len(r["numbers"]) for r in existing_data)
        success_msg = f"✅ API থেকে নম্বর এবং রেঞ্জ সিঙ্ক্রোনাইজ করা হয়েছে! মোট রেঞ্জ: {total_ranges}, মোট নম্বর: {total_numbers}"
        logger.info(success_msg)
        keyboard = []
        if str(chat_id) == str(ADMIN_CHAT_ID):
            keyboard.append([InlineKeyboardButton("সিঙ্ক করুন", callback_data="sync_now")])
        keyboard.append([InlineKeyboardButton("সকল ডিলিট করুন", callback_data="confirm_delete_all")])
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        await send_telegram_message(success_msg, chat_id, reply_markup=reply_markup)
        return True
    
    except Exception as e:
        error_msg = f"❌ API sync error: {str(e)}"
        logger.error(error_msg)
        await send_telegram_message(error_msg, chat_id)
        return False

async def fetch_number_list(session, csrf_token, range_value):
    """নাম্বারের লিস্ট ফেচ করা (পেজিনেশন সহ)"""
    post_data = {
        "_token": csrf_token,
        "start": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),  # গত ৭ দিনের ডাটা
        "end": datetime.now().strftime("%Y-%m-%d"),
        "range": range_value,
        "draw": 1,
        "length": 100  # প্রতি পেজে ১০০টি নাম্বার
    }
    
    headers = SMS_HEADERS.copy()
    headers["x-csrf-token"] = csrf_token
    
    max_retries = 3
    page = 0
    numbers = []
    
    while True:
        post_data["start"] = page * post_data["length"]
        for attempt in range(max_retries):
            try:
                logger.info(f"নাম্বার লিস্ট ফেচ করার জন্য রিকোয়েস্ট পাঠানো হচ্ছে (পেজ {page}, চেষ্টা {attempt + 1}/{max_retries}): রেঞ্জ={range_value}")
                response = session.post(SMS_LIST_URL, headers=headers, data=post_data, timeout=10)
                logger.info(f"নাম্বার লিস্ট রেসপন্স স্ট্যাটাস কোড: {response.status_code}")
                
                if not response.ok:
                    error_msg = f"❌ নাম্বার লিস্ট ফেচ ব্যর্থ! রেঞ্জ={range_value}, স্ট্যাটাস কোড: {response.status_code}"
                    logger.error(error_msg)
                    if response.status_code in [401, 403]:
                        return "SESSION_EXPIRED", []
                    if attempt < max_retries - 1:
                        await asyncio.sleep(5)
                        continue
                    return None, []
                
                soup = BeautifulSoup(response.text, "html.parser")
                number_cards = soup.find_all("div", class_="card card-body border-bottom bg-100 p-2 rounded-0")
                logger.info(f"Found {len(number_cards)} number cards for range {range_value}")
                
                if not number_cards:
                    debug_file = os.path.join(DEBUG_LOG_DIR, f"empty_number_list_{range_value}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
                    with open(debug_file, "w", encoding="utf-8") as f:
                        f.write(response.text)
                    logger.error(f"রেসপন্স সংরক্ষণ করা হয়েছে: {debug_file}")
                
                for card in number_cards:
                    number_div = card.find("div", class_="col-sm-4 border-bottom border-sm-bottom-0 pb-2 pb-sm-0 mb-2 mb-sm-0")
                    if number_div:
                        number = str(number_div.get_text(strip=True))
                        logger.info(f"Extracted number: {number}")
                        onclick = number_div.get("onclick", "")
                        id_number_match = re.search(r"'(\d+)','(\d+)'", onclick)
                        id_number = id_number_match.group(2) if id_number_match else ""
                        numbers.append({"number": number, "id_number": id_number})
                
                if len(number_cards) < post_data["length"]:
                    break
                
                page += 1
                break  # Exit retry loop if successful
                
            except Exception as e:
                error_msg = f"❌ নাম্বার লিস্ট ফেচ করতে সমস্যা: রেঞ্জ={range_value}, ত্রুটি: {str(e)}"
                logger.error(error_msg)
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)
                continue
        
        if len(number_cards) < post_data["length"]:
            break
    
    if numbers:
        logger.info(f"নাম্বার লিস্ট ফেচ সফল: {len(numbers)}টি নাম্বার পাওয়া গেছে")
        return response.text, numbers
    else:
        error_msg = f"❌ কোনো নাম্বার পাওয়া যায়নি! রেঞ্জ={range_value}"
        logger.error(error_msg)
        return None, []

async def fetch_sms_details(session, csrf_token, number, range_value, id_number):
    """নির্দিষ্ট নাম্বারের SMS বিস্তারিত ফেচ করা"""
    post_data = {
        "_token": csrf_token,
        "Number": str(number),
        "Range": str(range_value),
        "id_number": id_number
    }
    
    headers = SMS_HEADERS.copy()
    headers["x-csrf-token"] = csrf_token
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            logger.info(f"এসএমএস বিস্তারিত ফেচ করার জন্য রিকোয়েস্ট পাঠানো হচ্ছে (চেষ্টা {attempt + 1}/{max_retries}): নাম্বার={number}, রেঞ্জ={range_value}, id_number={id_number}")
            response = session.post(SMS_DETAILS_URL, headers=headers, data=post_data, timeout=10)
            logger.info(f"এসএমএস বিস্তারিত রেসপন্স স্ট্যাটাস কোড: {response.status_code}")
            
            debug_file = os.path.join(DEBUG_LOG_DIR, f"sms_raw_{number}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
            with open(debug_file, "w", encoding="utf-8") as f:
                f.write(response.text)
            logger.info(f"Raw response saved: {debug_file}")
            
            if not response.ok:
                error_msg = f"❌ এসএমএস বিস্তারিত ফেচ ব্যর্থ! নাম্বার={number}, রেঞ্জ={range_value}, স্ট্যাটাস কোড: {response.status_code}"
                logger.error(error_msg)
                if response.status_code in [401, 403]:
                    return "SESSION_EXPIRED"
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)
                    continue
                return None
            
            soup = BeautifulSoup(response.text, "html.parser")
            sms_content = soup.find("div", class_="card card-body border-bottom bg-soft-dark p-2 rounded-0")
            if not sms_content or not sms_content.get_text(strip=True):
                sms_content = soup.find("div", class_="card-body") or soup.find("div", class_="sms-content")
                if not sms_content or not sms_content.get_text(strip=True):
                    error_msg = f"❌ ফাঁকা এসএমএস কন্টেন্ট পাওয়া গেছে! নাম্বার={number}, রেঞ্জ={range_value}"
                    logger.error(error_msg)
                    debug_file = os.path.join(DEBUG_LOG_DIR, f"empty_sms_{number}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
                    with open(debug_file, "w", encoding="utf-8") as f:
                        f.write(response.text)
                    logger.error(f"রেসপন্স সংরক্ষণ করা হয়েছে: {debug_file}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(5)
                        continue
                    return None
            
            logger.info(f"এসএমএস বিস্তারিত ফেচ সফল: নাম্বার={number}")
            return response.text
        except Exception as e:
            error_msg = f"❌ এসএমএস বিস্তারিত ফেচ করতে সমস্যা: নাম্বার={number}, রেঞ্জ={range_value}, ত্রুটি: {str(e)}"
            logger.error(error_msg)
            if attempt < max_retries - 1:
                await asyncio.sleep(5)
            continue
    return None

async def process_sms(sms_html, number, range_value):
    """এসএমএস পার্স করে OTP বের করা এবং নতুন ফরম্যাটে মেসেজ পাঠানো"""
    try:
        soup = BeautifulSoup(sms_html, "html.parser")
        sms_cards = soup.find_all("div", class_="card card-body border-bottom bg-soft-dark p-2 rounded-0")
        logger.info(f"পাওয়া গেছে {len(sms_cards)}টি এসএমএস কার্ড")
        
        if not sms_cards:
            logger.info(f"কোনো এসএমএস কার্ড পাওয়া যায়নি! রেঞ্জ={range_value}, নাম্বার={number}")
            return
        
        dhaka_tz = pytz.timezone('Asia/Dhaka')
        current_time = datetime.now(dhaka_tz)
        
        for card in sms_cards:
            try:
                sms_text = card.find("p").get_text(strip=True) if card.find("p") else card.get_text(strip=True)
                logger.info(f"এসএমএস টেক্সট: {sms_text}")
                if not sms_text:
                    logger.info("এসএমএস টেক্সট ফাঁকা, স্কিপ করা হচ্ছে...")
                    continue
                
                sms_timestamp = card.find("span", class_="sms-date")
                timestamp_str = sms_timestamp.get_text(strip=True) if sms_timestamp else current_time.isoformat()
                try:
                    sms_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                    sms_time = sms_time.astimezone(dhaka_tz)
                except ValueError:
                    try:
                        sms_time = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                        sms_time = dhaka_tz.localize(sms_time)
                    except ValueError:
                        logger.warning(f"টাইমস্ট্যাম্প পার্স করা যায়নি: {timestamp_str}, বর্তমান সময় ব্যবহার করা হচ্ছে")
                        sms_time = current_time
                
                if current_time - sms_time > TIME_THRESHOLD:
                    logger.info(f"পুরানো এসএমএস (টাইমস্ট্যাম্প: {timestamp_str}), স্কিপ করা হচ্ছে...")
                    continue
                
                sms_id = hashlib.sha256(f"{number}{sms_text}".encode()).hexdigest()
                if sms_id in seen_sms:
                    logger.info(f"ডুপ্লিকেট এসএমঐস (ID: {sms_id}), স্কিপ করা হচ্ছে...")
                    continue
                
                phone_number = mask_phone_number(number)
                logger.info(f"Final phone number for message: {phone_number}")
                
                code_match = re.search(r"(\d{6}|\d{5}|\d{4}|\d{3}[- ]?\d{3})", sms_text)
                if code_match:
                    otp_code = code_match.group(0).replace("-", "").replace(" ", "")
                    if "WhatsApp" in sms_text:
                        service = "WhatsApp"
                    elif "Facebook" in sms_text or "FB-" in sms_text:
                        service = "Facebook"
                    else:
                        service = "Unknown"
                    
                    country = str(range_value).split()[0] if range_value else "Unknown"
                    formatted_time = current_time.strftime("%d %b %Y, %I:%M %p")
                    
                    message = (
                        f"✨ {service}: OTP ALERT! ✨\n\n"
                        f"🌎 Country: {country}\n"
                        f"⚙️ Service: {service}\n"
                        f"☎️ Number: {phone_number}\n"
                        f"🔑 OTP কোড: `{otp_code}`\n"
                        f"📝 Full Message: ```\n{sms_text}\n```\n"
                        f"🕒 Time: {formatted_time}\n\n"
                        f"🚀 Be Active, New OTP Loading...\n\n"
                        f"BAPPY KHAN"
                    )
                    
                    logger.info(f"Message to be sent: {message}")
                    await send_telegram_message(message, CHAT_ID, reply_markup=None)
                    seen_sms.add(sms_id)
                    save_seen_sms()
                    logger.info(f"OTP পাওয়া গেছে: {otp_code}, Service: {service}, SMS ID: {sms_id}")
                else:
                    logger.info("কোনো OTP পাওয়া যায়নি")
            except Exception as e:
                error_msg = f"❌ এসএমএস প্রসেস করতে সমস্যা: রেঞ্জ={range_value}, নাম্বার={number}, ত্রুটি: {str(e)}"
                logger.error(error_msg)
                await send_telegram_message(error_msg, CHAT_ID)
    except Exception as e:
        error_msg = f"❌ এসএমঐস পার্স করতে সমস্যা: রেঞ্জ={range_value}, নাম্বার={number}, ত্রুটি: {str(e)}"
        logger.error(error_msg)
        await send_telegram_message(error_msg, CHAT_ID)

async def wait_for_sms(session, csrf_token):
    """JSON ফাইল থেকে নাম্বার এবং রেঞ্জ নিয়ে OTP চেক করা"""
    last_no_range_message = 0
    message_interval = 300
    
    while True:
        logger.info("নতুন এসএমঐস চেক করা হচ্ছে...")
        try:
            with open(NUMBERS_RANGES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            initialize_numbers_ranges_file()
            data = {"ranges": []}
            logger.info("JSON ফাইল পাওয়া যায়নি, ডিফল্ট ফাইল তৈরি করা হয়েছে...")
        
        ranges = data.get("ranges", [])
        if not ranges:
            current_time = time.time()
            if current_time - last_no_range_message > message_interval:
                logger.info("কোনো রেঞ্জ পাওয়া যায়নি, মেসেজ পাঠানো হচ্ছে...")
                await send_telegram_message("⚠️ কোনো রেঞ্জ পাওয়া যায়নি। /add_range বা /sync ব্যবহার করুন।", CHAT_ID)
                last_no_range_message = current_time
            else:
                logger.info("কোনো রেঞ্জ পাওয়া যায়নি, তবে মেসেজ পাঠানো হয়নি (সময় ব্যবধানের কারণে)")
            await asyncio.sleep(2)
            continue
        
        total_numbers_processed = 0
        for range_item in ranges:
            range_value = str(range_item.get("range", ""))
            range_numbers = range_item.get("numbers", [])
            if not range_numbers:
                logger.info(f"রেঞ্জ {range_value} এর জন্য কোনো নাম্বার নেই, স্কিপ করা হচ্ছে...")
                continue
            
            number_list_html, numbers = await fetch_number_list(session, csrf_token, range_value)
            if number_list_html == "SESSION_EXPIRED":
                logger.info("সেশন অবৈধ, পুনরায় লগইন করা হচ্ছে...")
                session, csrf_token = login_and_get_csrf()
                if not session or not csrf_token:
                    logger.error("পুনরায় লগইন ব্যর্থ, ৫ সেকেন্ড অপেক্ষা...")
                    await asyncio.sleep(5)
                    continue
                number_list_html, numbers = await fetch_number_list(session, csrf_token, range_value)
            
            if not numbers:
                logger.info(f"রেঞ্জ {range_value} এর জন্য কোনো নাম্বার পাওয়া যায়নি, পরবর্তী রেঞ্জে যাওয়া হচ্ছে...")
                continue
            
            for number_info in numbers:
                number = str(number_info["number"])
                id_number = str(number_info["id_number"])
                sms_html = await fetch_sms_details(session, csrf_token, number, range_value, id_number)
                if sms_html == "SESSION_EXPIRED":
                    logger.info("সেশন অবৈধ, পুনরায় লগইন করা হচ্ছে...")
                    session, csrf_token = login_and_get_csrf()
                    if not session or not csrf_token:
                        logger.error("পুনরায় লগইন ব্যর্থ, ৫ সেকেন্ড অপেক্ষা...")
                        await asyncio.sleep(5)
                        continue
                    sms_html = await fetch_sms_details(session, csrf_token, number, range_value, id_number)
                
                if sms_html:
                    await process_sms(sms_html, number, range_value)
                else:
                    logger.info(f"নাম্বার {number} এর জন্য এসএমঐস ফেচ ব্যর্থ, পরবর্তী নাম্বারে যাওয়া হচ্ছে...")
                
                total_numbers_processed += 1
        
        logger.info(f"মোট নাম্বার প্রসেস করা হয়েছে: {total_numbers_processed}")
        logger.info("২ সেকেন্ড অপেক্ষা করা হচ্ছে...")
        await asyncio.sleep(2)

async def handle_bot_updates(update, session, csrf_token):
    """টেলিগ্রাম বট আপডেট হ্যান্ডল করা"""
    global pending_ranges
    try:
        if update.message:
            message = update.message
            chat_id = message.chat.id
            user_id = message.from_user.id
            username = message.from_user.username or "Unknown"
            text = message.text or ""
            logger.info(f"মেসেজ পাওয়া গেছে: {text} | Chat ID: {chat_id} | User ID: {user_id} | Username: @{username}")
            
            try:
                with open(NUMBERS_RANGES_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except FileNotFoundError:
                initialize_numbers_ranges_file()
                data = {"ranges": []}
            
            ranges = data.get("ranges", [])
            
            # অ্যাডমিন চেক ফাংশন
            def is_admin(chat_id, user_id):
                return str(chat_id) == str(ADMIN_CHAT_ID) and user_id in ADMIN_USER_IDS
            
            # /add_admin কমান্ড
            if text.startswith(("/add_admin", "/add_admin@dxsmsreceiver_bot")):
                if not is_admin(chat_id, user_id):
                    await bot.send_message(
                        chat_id=chat_id,
                        text="❌ এই কমান্ড শুধুমাত্র অ্যাডমিন ব্যবহার করতে পারেন!"
                    )
                    logger.warning(f"Non-admin attempted /add_admin: User ID: {user_id}, Username: @{username}")
                    return
                parts = text.split()
                if len(parts) != 2:
                    await bot.send_message(
                        chat_id=chat_id,
                        text="⚠️ একটি বৈধ ইউজার আইডি দিন। উদাহরণ: /add_admin 123456789"
                    )
                    return
                new_admin_id = parts[1].strip()
                if not re.match(r"^\d+$", new_admin_id):
                    await bot.send_message(
                        chat_id=chat_id,
                        text="❌ ইউজার আইডি একটি পজিটিভ সংখ্যা হতে হবে।"
                    )
                    return
                new_admin_id = int(new_admin_id)
                if new_admin_id in ADMIN_USER_IDS:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"ℹ️ ইউজার আইডি {new_admin_id} ইতিমধ্যে একজন অ্যাডমিন।"
                    )
                    return
                ADMIN_USER_IDS.append(new_admin_id)
                save_admins()
                logger.info(f"নতুন অ্যাডমিন যোগ করা হয়েছে: {new_admin_id}, যোগ করেছেন: {user_id} (@{username})")
                formatted_time = datetime.now(pytz.timezone('Asia/Dhaka')).strftime("%d %b %Y, %I:%M %p")
                await bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"✅ নতুন অ্যাডমিন যোগ করা হয়েছে: ইউজার আইডি `{new_admin_id}`\n"
                        f"🕒 সময়: {formatted_time}\n"
                        f"🚀 এখন তিনি অ্যাডমিন কমান্ড ব্যবহার করতে পারবেন।\n\n"
                        f"~ BAPPY KHAN"
                    ),
                    parse_mode="Markdown"
                )
                return
            
            # /remove_admin কমান্ড
            if text.startswith(("/remove_admin", "/remove_admin@dxsmsreceiver_bot")):
                if not is_admin(chat_id, user_id):
                    await bot.send_message(
                        chat_id=chat_id,
                        text="❌ এই কমান্ড শুধুমাত্র অ্যাডমিন ব্যবহার করতে পারেন!"
                    )
                    logger.warning(f"Non-admin attempted /remove_admin: User ID: {user_id}, Username: @{username}")
                    return
                parts = text.split()
                if len(parts) != 2:
                    await bot.send_message(
                        chat_id=chat_id,
                        text="⚠️ একটি বৈধ ইউজার আইডি দিন। উদাহরণ: /remove_admin 123456789"
                    )
                    return
                admin_id_to_remove = parts[1].strip()
                if not re.match(r"^\d+$", admin_id_to_remove):
                    await bot.send_message(
                        chat_id=chat_id,
                        text="❌ ইউজার আইডি একটি পজিটিভ সংখ্যা হতে হবে।"
                    )
                    return
                admin_id_to_remove = int(admin_id_to_remove)
                if admin_id_to_remove not in ADMIN_USER_IDS:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"ℹ️ ইউজার আইডি {admin_id_to_remove} একজন অ্যাডমিন নয়।"
                    )
                    return
                if len(ADMIN_USER_IDS) <= 1:
                    await bot.send_message(
                        chat_id=chat_id,
                        text="❌ শেষ অ্যাডমিনকে রিমুভ করা যাবে না। অন্তত একজন অ্যাডমিন থাকতে হবে।"
                    )
                    return
                ADMIN_USER_IDS.remove(admin_id_to_remove)
                save_admins()
                logger.info(f"অ্যাডমিন রিমুভ করা হয়েছে: {admin_id_to_remove}, রিমুভ করেছেন: {user_id} (@{username})")
                formatted_time = datetime.now(pytz.timezone('Asia/Dhaka')).strftime("%d %b %Y, %I:%M %p")
                await bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"✅ অ্যাডমিন রিমুভ করা হয়েছে: ইউজার আইডি `{admin_id_to_remove}`\n"
                        f"🕒 সময়: {formatted_time}\n"
                        f"🚀 তিনি আর অ্যাডমিন কমান্ড ব্যবহার করতে পারবেন না।\n\n"
                        f"~ BAPPY KHAN"
                    ),
                    parse_mode="Markdown"
                )
                return
            
            # /check_id কমান্ড
            if text.startswith(("/check_id", "/check_id@dxsmsreceiver_bot")):
                if not is_admin(chat_id, user_id):
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"❌ এই কমান্ড শুধুমাত্র অ্যাডমিন ব্যবহার করতে পারেন! (User ID: {user_id})"
                    )
                    logger.warning(f"Non-admin attempted /check_id: User ID: {user_id}, Username: @{username}")
                    return
                parts = text.split()
                if len(parts) < 2:
                    await bot.send_message(
                        chat_id=chat_id,
                        text="⚠️ আইডি দিন। উদাহরণ: /check_id -1002639503570"
                    )
                    return
                input_id = parts[1].strip()
                if input_id == str(ADMIN_CHAT_ID):
                    msg = f"✅ এটি অ্যাডমিন চ্যাট আইডি: {input_id}\nঅ্যাডমিন কমান্ড ব্যবহার করা যাবে।"
                else:
                    msg = f"ℹ️ এটি নন-অ্যাডমিন চ্যাট আইডি: {input_id}\nঅ্যাডমিন কমান্ড ব্যবহার করা যাবে না।"
                await bot.send_message(
                    chat_id=chat_id,
                    text=msg
                )
                logger.info(f"চেক করা আইডি: {input_id} | User ID: {user_id} | Chat ID: {chat_id}")
                return
            
            # /sync কমান্ড
            elif text.startswith(("/sync", "/sync@dxsmsreceiver_bot")):
                if not is_admin(chat_id, user_id):
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"❌ এই কমান্ড শুধুমাত্র অ্যাডমিন ব্যবহার করতে পারেন! (User ID: {user_id})"
                    )
                    logger.warning(f"Non-admin attempted /sync: User ID: {user_id}, Username: @{username}")
                    return
                await bot.send_message(
                    chat_id=chat_id,
                    text="🔄 API থেকে নম্বর এবং রেঞ্জ সিঙ্ক্রোনাইজ করা হচ্ছে..."
                )
                success = await sync_numbers_from_api(session, csrf_token, chat_id)
                if not success:
                    await bot.send_message(
                        chat_id=chat_id,
                        text="❌ সিঙ্ক্রোনাইজেশন ব্যর্থ! বিস্তারিত লগ দেখুন।"
                    )
            
            # /delete_all কমান্ড
            elif text.startswith(("/delete_all", "/delete_all@dxsmsreceiver_bot")):
                if not is_admin(chat_id, user_id):
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"❌ এই কমান্ড শুধুমাত্র অ্যাডমিন ব্যবহার করতে পারেন! (User ID: {user_id})"
                    )
                    logger.warning(f"Non-admin attempted /delete_all: User ID: {user_id}, Username: @{username}")
                    return
                keyboard = [
                    [InlineKeyboardButton("হ্যাঁ, সব ডিলিট করুন", callback_data="delete_all")],
                    [InlineKeyboardButton("না, বাতিল করুন", callback_data="cancel_delete")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await bot.send_message(
                    chat_id=chat_id,
                    text="আপনি কি নিশ্চিত যে সকল নম্বর এবং রেঞ্জ ডিলিট করতে চান?",
                    reply_markup=reply_markup
                )
            
            # /add_range কমান্ড
            elif text.startswith(("/add_range", "/add_range@dxsmsreceiver_bot")):
                if not is_admin(chat_id, user_id):
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"❌ এই কমান্ড শুধুমাত্র অ্যাডমিন ব্যবহার করতে পারেন! (User ID: {user_id})"
                    )
                    logger.warning(f"Non-admin attempted /add_range: User ID: {user_id}, Username: @{username}")
                    return
                pending_ranges[chat_id] = {"range": None, "numbers": []}
                await bot.send_message(
                    chat_id=chat_id,
                    text="রেঞ্জ দিন (যেমন, BOLIVIA 1926)।"
                )
            
            # /remove_range কমান্ড
            elif text.startswith(("/remove_range", "/remove_range@dxsmsreceiver_bot")):
                if not is_admin(chat_id, user_id):
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"❌ এই কমান্ড শুধুমাত্র অ্যাডমিন ব্যবহার করতে পারেন! (User ID: {user_id})"
                    )
                    logger.warning(f"Non-admin attempted /remove_range: User ID: {user_id}, Username: @{username}")
                    return
                numbers, ranges_list = load_numbers_ranges()
                if ranges_list:
                    keyboard = [[InlineKeyboardButton(range_val, callback_data=f"remove_{range_val}")] for range_val in ranges_list]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await bot.send_message(
                        chat_id=chat_id,
                        text="মুছে ফেলতে একটি রেঞ্জ বেছে নিন:",
                        reply_markup=reply_markup
                    )
                else:
                    await bot.send_message(
                        chat_id=chat_id,
                        text="কোনো রেঞ্জ যুক্ত করা হয়নি।"
                    )
            
            # /start কমান্ড
            elif text.startswith(("/start", "/start@dxsmsreceiver_bot")):
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"👋 স্বাগতম, @{username}! (User ID: {user_id})\nরেঞ্জ এবং নাম্বার যুক্ত করতে /add_range, API থেকে সিঙ্ক করতে /sync (শুধু অ্যাডমিন), বা সব ডিলিট করতে /delete_all (শুধু অ্যাডমিন) ব্যবহার করুন।"
                )
            
            # /list_ranges কমান্ড
            elif text.startswith(("/list_ranges", "/list_ranges@dxsmsreceiver_bot")):
                if not is_admin(chat_id, user_id):
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"❌ এই কমান্ড শুধুমাত্র অ্যাডমিন ব্যবহার করতে পারেন! (User ID: {user_id})"
                    )
                    logger.warning(f"Non-admin attempted /list_ranges: User ID: {user_id}, Username: @{username}")
                    return
                numbers, ranges_list = load_numbers_ranges()
                if ranges:
                    keyboard = []
                    for r in ranges:
                        range_name = r["range"]
                        num_count = len(r["numbers"])
                        keyboard.append([InlineKeyboardButton(f"{range_name}: {num_count}টি নাম্বার", callback_data=f"view_{range_name}"),
                                         InlineKeyboardButton("🗑️ ডিলিট", callback_data=f"confirm_delete_range_{range_name}")])
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await bot.send_message(
                        chat_id=chat_id,
                        text="যুক্ত রেঞ্জ (ডিলিট করতে বাটনে ক্লিক করুন):",
                        reply_markup=reply_markup
                    )
                else:
                    await bot.send_message(
                        chat_id=chat_id,
                        text="কোনো রেঞ্জ যুক্ত করা হয়নি।"
                    )
            
            # পেন্ডিং রেঞ্জ হ্যান্ডলিং
            elif chat_id in pending_ranges and pending_ranges[chat_id].get("range") is not None:
                if not text:
                    logger.info("ফাঁকা মেসেজ, স্কিপ করা হচ্ছে...")
                    return
                logger.info(f"Received text: '{text}' (length: {len(text)})")
                cleaned_text = text.strip()
                if cleaned_text in ["/add_range", "/add_range@dxsmsreceiver_bot"]:
                    if not is_admin(chat_id, user_id):
                        await bot.send_message(
                            chat_id=chat_id,
                            text=f"❌ এই কমান্ড শুধুমাত্র অ্যাডমিন ব্যবহার করতে পারেন! (User ID: {user_id})"
                        )
                        logger.warning(f"Non-admin attempted /add_range in pending range: User ID: {user_id}, Username: @{username}")
                        return
                    logger.info(f"Resetting pending_ranges for chat_id {chat_id}: {pending_ranges[chat_id]}")
                    pending_ranges[chat_id] = {"range": None, "numbers": []}
                    logger.info(f"After reset, pending_ranges for chat_id {chat_id}: {pending_ranges[chat_id]}")
                    await bot.send_message(
                        chat_id=chat_id,
                        text="রেঞ্জ দিন (যেমন, BOLIVIA 1926)।"
                    )
                    return
                numbers_input = text.split("\n")
                range_value = pending_ranges[chat_id]["range"]
                valid_numbers = []
                invalid_numbers = []
                for number in numbers_input:
                    number = str(number).strip()
                    if not number:
                        continue
                    if validate_phone_number(number):
                        valid_numbers.append(number)
                        pending_ranges[chat_id]["numbers"].append(number)
                        logger.info(f"নাম্বার যোগ করা হয়েছে: {number}, মোট নাম্বার: {len(pending_ranges[chat_id]['numbers'])}")
                    else:
                        invalid_numbers.append(number)
                if valid_numbers:
                    existing_range = next((item for item in ranges if item["range"] == range_value), None)
                    if existing_range:
                        existing_range["numbers"].extend([num for num in valid_numbers if num not in existing_range["numbers"]])
                    else:
                        ranges.append({"range": range_value, "numbers": valid_numbers})
                    save_numbers_ranges(ranges)
                    valid_msg = f"✅ নাম্বার গ্রহণ করা হয়েছে: {', '.join(valid_numbers)}\nরেঞ্জ এবং নাম্বার সেভ করা হয়েছে: {range_value} ({len(pending_ranges[chat_id]['numbers'])}টি নাম্বার)\nনতুন নাম্বার দিন, অথবা নতুন রেঞ্জের জন্য /add_range দিন।"
                    await bot.send_message(chat_id=chat_id, text=valid_msg)
                if invalid_numbers:
                    invalid_msg = f"⚠️ অবৈধ নাম্বার! ৮-১২ ডিজিটের নাম্বার দিন। অবৈধ নাম্বার: {', '.join(invalid_numbers)}"
                    await bot.send_message(chat_id=chat_id, text=invalid_msg)
                return
            
            # পেন্ডিং রেঞ্জের জন্য রেঞ্জ ইনপুট
            elif chat_id in pending_ranges and pending_ranges[chat_id]["range"] is None:
                if not is_admin(chat_id, user_id):
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"❌ এই ক্রিয়া শুধুমাত্র অ্যাডমিন ব্যবহার করতে পারেন! (User ID: {user_id})"
                    )
                    logger.warning(f"Non-admin attempted to input range: User ID: {user_id}, Username: @{username}")
                    return
                pending_ranges[chat_id]["range"] = text.strip()
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"✅ রেঞ্জ গ্রহণ করা হয়েছে: {text}\nএখন নাম্বার দিন (প্রতি লাইনে একটি)।"
                )
        
        # ইনলাইন কলব্যাক হ্যান্ডলিং
        if update.callback_query:
            query = update.callback_query
            data = query.data
            chat_id = query.message.chat.id
            user_id = query.from_user.id
            username = query.from_user.username or "Unknown"
            logger.info(f"ইনলাইন বাটন ক্লিক করা হয়েছে: {data} | Chat ID: {chat_id} | User ID: {user_id} | Username: @{username}")
            await query.answer()
            
            # অ্যাডমিন চেক
            def is_admin(chat_id, user_id):
                return str(chat_id) == str(ADMIN_CHAT_ID) and user_id in ADMIN_USER_IDS
            
            if data == "sync_now":
                if not is_admin(chat_id, user_id):
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"❌ এই ফিচার শুধুমাত্র অ্যাডমিন ব্যবহার করতে পারেন! (User ID: {user_id})"
                    )
                    logger.warning(f"Non-admin attempted sync_now: User ID: {user_id}, Username: @{username}")
                    return
                await bot.send_message(
                    chat_id=chat_id,
                    text="🔄 API থেকে নম্বর এবং রেঞ্জ সিঙ্ক্রোনাইজ করা হচ্ছে..."
                )
                success = await sync_numbers_from_api(session, csrf_token, chat_id)
                if not success:
                    await bot.send_message(
                        chat_id=chat_id,
                        text="❌ সিঙ্ক্রোনাইজেশন ব্যর্থ! বিস্তারিত লগ দেখুন।"
                    )
            elif data == "confirm_delete_all":
                if not is_admin(chat_id, user_id):
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"❌ এই ফিচার শুধুমাত্র অ্যাডমিন ব্যবহার করতে পারেন! (User ID: {user_id})"
                    )
                    logger.warning(f"Non-admin attempted confirm_delete_all: User ID: {user_id}, Username: @{username}")
                    return
                keyboard = [
                    [InlineKeyboardButton("হ্যাঁ, সব ডিলিট করুন", callback_data="delete_all")],
                    [InlineKeyboardButton("না, বাতিল করুন", callback_data="cancel_delete")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await bot.send_message(
                    chat_id=chat_id,
                    text="আপনি কি নিশ্চিত যে সকল নম্বর এবং রেঞ্জ ডিলিট করতে চান?",
                    reply_markup=reply_markup
                )
            elif data == "delete_all":
                if not is_admin(chat_id, user_id):
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"❌ এই ফিচার শুধুমাত্র অ্যাডমিন ব্যবহার করতে পারেন! (User ID: {user_id})"
                    )
                    logger.warning(f"Non-admin attempted delete_all: User ID: {user_id}, Username: @{username}")
                    return
                success = delete_all_numbers_ranges()
                if success:
                    await bot.send_message(
                        chat_id=chat_id,
                        text="✅ সকল নম্বর এবং রেঞ্জ ডিলিট করা হয়েছে!"
                    )
                else:
                    await bot.send_message(
                        chat_id=chat_id,
                        text="❌ সকল নম্বর এবং রেঞ্জ ডিলিট করতে সমস্যা! বিস্তারিত লগ দেখুন।"
                    )
            elif data.startswith("confirm_delete_range_"):
                if not is_admin(chat_id, user_id):
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"❌ এই ফিচার শুধুমাত্র অ্যাডমিন ব্যবহার করতে পারেন! (User ID: {user_id})"
                    )
                    logger.warning(f"Non-admin attempted confirm_delete_range: User ID: {user_id}, Username: @{username}")
                    return
                try:
                    range_value = data.split("confirm_delete_range_")[1]
                    keyboard = [[InlineKeyboardButton("হ্যাঁ", callback_data=f"delete_range_{range_value}"),
                                 InlineKeyboardButton("না", callback_data="cancel_delete")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"আপনি কি নিশ্চিত যে রেঞ্জটি মুছে ফেলবেন: {range_value}?",
                        reply_markup=reply_markup
                    )
                except IndexError:
                    logger.error(f"Invalid callback data: {data}")
                    await bot.send_message(chat_id=chat_id, text="❌ অবৈধ কলব্যাক ডাটা!")
            elif data.startswith("delete_range_"):
                if not is_admin(chat_id, user_id):
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"❌ এই ফিচার শুধুমাত্র অ্যাডমিন ব্যবহার করতে পারেন! (User ID: {user_id})"
                    )
                    logger.warning(f"Non-admin attempted delete_range: User ID: {user_id}, Username: @{username}")
                    return
                try:
                    range_value = data.split("delete_range_")[1]
                    logger.info(f"Processing delete_range_ for range: {range_value}")
                    try:
                        with open(NUMBERS_RANGES_FILE, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        ranges = data.get("ranges", [])
                        ranges = [item for item in ranges if item["range"].strip() != range_value.strip()]
                        save_numbers_ranges(ranges)
                        await bot.send_message(
                            chat_id=chat_id,
                            text=f"✅ রেঞ্জ মুছে ফেলা হয়েছে: {range_value}"
                        )
                    except Exception as e:
                        logger.error(f"রেঞ্জ ডিলিট করতে সমস্যা: {str(e)}")
                        await send_telegram_message(f"❌ রেঞ্জ ডিলিট করতে সমস্যা: {str(e)}", chat_id)
                except IndexError:
                    logger.error(f"Invalid callback data: {data}")
                    await bot.send_message(chat_id=chat_id, text="❌ অবৈধ কলব্যাক ডাটা!")
            elif data == "cancel_delete":
                await bot.send_message(
                    chat_id=chat_id,
                    text="❌ ডিলিট বাতিল করা হয়েছে।"
                )
            elif data.startswith("view_"):
                if not is_admin(chat_id, user_id):
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"❌ এই ফিচার শুধুমাত্র অ্যাডমিন ব্যবহার করতে পারেন! (User ID: {user_id})"
                    )
                    logger.warning(f"Non-admin attempted view_range: User ID: {user_id}, Username: @{username}")
                    return
                try:
                    range_value = data[5:]
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"রেঞ্জ: {range_value} (বিস্তারিত দেখার ফিচার আসছে...)"
                    )
                except IndexError:
                    logger.error(f"Invalid callback data: {data}")
                    await bot.send_message(chat_id=chat_id, text="❌ অবৈধ কলব্যাক ডাটা!")
    except Exception as e:
        logger.error(f"বট আপডেট হ্যান্ডল করতে সমস্যা: {str(e)}")
        await send_telegram_message(f"❌ বটে সমস্যা: {str(e)}", chat_id)

async def run_bot(session, csrf_token):
    """টেলিগ্রাম বট লুপ"""
    offset = None
    last_reset = time.time()
    reset_interval = 600
    while True:
        try:
            if time.time() - last_reset > reset_interval:
                logger.info("অফসেট রিসেট করা হচ্ছে...")
                offset = None
                last_reset = time.time()
            logger.info(f"টেলিগ্রাম আপডেট ফেচ করা হচ্ছে... সময়: {datetime.now()}")
            updates = await bot.get_updates(offset=offset, timeout=30)
            logger.info(f"আপডেট পাওয়া গেছে: {len(updates)}টি")
            for update in updates:
                logger.info(f"আপডেট প্রসেস করা হচ্ছে: update_id={update.update_id}")
                await handle_bot_updates(update, session, csrf_token)
                offset = update.update_id + 1
            await asyncio.sleep(1)
        except telegram.error.InvalidToken:
            logger.error("টেলিগ্রাম বট টোকেন ভুল। BotFather থেকে টোকেন চেক করুন।")
            await send_telegram_message("❌ টেলিগ্রাম বট টোকেন ভুল। BotFather থেকে টোকেন চেক করুন।", CHAT_ID)
            await asyncio.sleep(5)
        except telegram.error.NetworkError as e:
            logger.error(f"নেটওয়ার্ক সমস্যা: {str(e)}")
            await send_telegram_message(f"❌ নেটওয়ার্ক সমস্যা: {str(e)}", CHAT_ID)
            await asyncio.sleep(5)
        except telegram.error.TelegramError as e:
            logger.error(f"টেলিগ্রাম API সমস্যা: {str(e)}")
            await send_telegram_message(f"❌ টেলিগ্রাম API সমস্যা: {str(e)}", CHAT_ID)
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"বট লুপে সমস্যা: {str(e)}")
            await send_telegram_message(f"❌ বট লুপে সমস্যা: {str(e)}", CHAT_ID)
            await asyncio.sleep(5)
async def main():
    """মূল ফাংশন"""
    load_seen_sms()
    
    await send_startup_alert()
    
    session, csrf_token = login_and_get_csrf()
    while not session or not csrf_token:
        logger.error("লগইন ব্যর্থ, ৫ সেকেন্ড পর পুনরায় চেষ্টা...")
        await asyncio.sleep(5)
        session, csrf_token = login_and_get_csrf()
    
    await sync_numbers_from_api(session, csrf_token)
    
    bot_task = asyncio.create_task(run_bot(session, csrf_token))
    sms_task = asyncio.create_task(wait_for_sms(session, csrf_token))
    
    try:
        sync_interval = 300  # ৫ মিনিট = ৩০০ সেকেন্ড
        last_sync = time.time()
        
        while True:
            if time.time() - last_sync > sync_interval:
                logger.info("Starting periodic API synchronization...")
                await sync_numbers_from_api(session, csrf_token, ADMIN_CHAT_ID)
                last_sync = time.time()
            
            if not session or not csrf_token:
                logger.info("Session invalid, re-logging in...")
                session, csrf_token = login_and_get_csrf()
                if not session or not csrf_token:
                    logger.error("Re-login failed, waiting 5 seconds...")
                    await asyncio.sleep(5)
                    continue
            
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("কোড বন্ধ করা হয়েছে।")
        bot_task.cancel()
        sms_task.cancel()
        try:
            await bot_task
            await sms_task
        except asyncio.CancelledError:
            logger.info("টাস্কগুলো বাতিল করা হয়েছে।")
    except Exception as e:
        error_msg = f"❌ কোডে সমস্যা: {str(e)}"
        logger.error(error_msg)
        await send_telegram_message(error_msg, CHAT_ID)
        bot_task.cancel()
        sms_task.cancel()
        try:
            await bot_task
            await sms_task
        except asyncio.CancelledError:
            logger.info("টাস্কগুলো বাতিল করা হয়েছে।")

if __name__ == "__main__":
    logger.info("কোড শুরু হচ্ছে...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    except RuntimeError as e:
        logger.error(f"ইভেন্ট লুপ সমস্যা: {str(e)}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
    finally:
        loop.close()
