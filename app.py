from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import NoSuchElementException, TimeoutException
import os
import time
import re
import base64
import joblib
import numpy as np
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

class InstagramScraper:
    def __init__(self):
        self.driver = None
        self.model = None
        self.scaler = None
        self.expected_features = None
        self.load_model()
    
    def load_model(self):
        try:
            self.model = joblib.load('random_forest_model.joblib')
            self.scaler = joblib.load('scaler.joblib')
            with open('feature_names.txt', 'r') as f:
                self.expected_features = f.read().split(',')
            logger.info("ML model loaded")
        except Exception as e:
            logger.error(f"Model load failed: {str(e)}")
            raise

    def init_driver(self):
        """EXACT replica of your Edge setup but for Chrome"""
        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            chrome_options.add_argument(f"--user-agent={ua}")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")

            service = Service(executable_path="/usr/local/bin/chromedriver")
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            
            self.driver.get("https://www.instagram.com/")
            logger.info("Chrome driver ready")
            return True
        except Exception as e:
            logger.error(f"Driver failed: {str(e)}")
            return False

    def login(self):
        """YOUR EXACT login logic"""
        try:
            time.sleep(2)
            username = os.getenv('INSTAGRAM_USERNAME')
            password = os.getenv('INSTAGRAM_PASSWORD')
            
            if not username or not password:
                raise Exception("No credentials")

            username_field = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input[name='username']")))
            password_field = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input[name='password']")))

            username_field.clear()
            username_field.send_keys(username)
            time.sleep(1)
            password_field.clear()
            password_field.send_keys(password)
            password_field.send_keys(Keys.ENTER)
            logger.info("Login submitted")
            time.sleep(5)

            # Handle pop-up
            try:
                not_now_button = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Not Now')]"))
                )
                not_now_button.click()
                logger.info("Clicked pop-up")
                time.sleep(2)
            except TimeoutException:
                pass
                
            return True
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            return False

    def extract_profile_picture(self, username):
        """YOUR EXACT image extraction with base64"""
        try:
            pic = self.driver.find_element(By.CSS_SELECTOR, "img[alt$=\"'s profile picture\"]")
            src = pic.get_attribute('src')

            js_script = """
                var img = arguments[0];
                var canvas = document.createElement('canvas');
                canvas.width = img.naturalWidth;
                canvas.height = img.naturalHeight;
                canvas.getContext('2d').drawImage(img, 0, 0);
                return canvas.toDataURL('image/jpeg');
            """
            base64_data = self.driver.execute_script(js_script, pic)
            base64_content = base64_data.split(',')[1]

            # Save image
            image_data = base64.b64decode(base64_content)
            if not os.path.exists('profile_pics'):
                os.makedirs('profile_pics')
            image_path = os.path.join('profile_pics', f'{username}.jpg')
            with open(image_path, 'wb') as f:
                f.write(image_data)

            # Default pic check
            if 'ig_cache_key=YW5vbnltb3VzX3Byb2ZpbGVfcGlj' in src:
                profile_pic = 0
            else:
                profile_pic = 1

            return profile_pic
                
        except NoSuchElementException:
            return 0
        except Exception as e:
            logger.error(f"Picture error: {str(e)}")
            return 0

    def extract_full_name(self, username):
        """YOUR EXACT name extraction logic"""
        try:
            selectors = [
                "//header//div[2]//span",
                "//header//h1", 
                "//header//div[contains(@class, '_aacx')]//span",
                "//header//div[contains(@class, '_aacl')]",
                "//header//div[contains(@class, '_aac')]//span[1]",
            ]
            
            full_name_raw = ""
            
            for selector in selectors:
                try:
                    element = self.driver.find_element(By.XPATH, selector)
                    text = element.text.strip()
                    
                    if (text and 
                        not text.startswith('#') and
                        "posts" not in text.lower() and
                        "followers" not in text.lower() and
                        "following" not in text.lower() and
                        1 < len(text) < 50):
                        
                        full_name_raw = text
                        break
                except NoSuchElementException:
                    continue
            
            if full_name_raw:
                uname_cleaned = re.sub(r'[^\w]', '', username)
                if uname_cleaned and uname_cleaned.lower() in full_name_raw.lower():
                    pattern = r'\s*' + re.escape(uname_cleaned) + r'\s*$'
                    full_name = re.sub(pattern, '', full_name_raw, flags=re.IGNORECASE).strip()
                else:
                    full_name = full_name_raw
                
                if len(full_name.split()) > 2:
                    full_name = " ".join(full_name.split()[:2])
            else:
                full_name = ""
                
            return full_name
        except Exception as e:
            logger.error(f"Name error: {e}")
            return ""

    def get_stat(self, kind):
        """YOUR EXACT stats extraction"""
        try:
            if kind == "posts":
                el = self.driver.find_element(By.XPATH, "//div[span[contains(text(),'posts')]]//span/span")
            elif kind == "followers":
                el = self.driver.find_element(By.XPATH, "//a[contains(@href,'followers')]//span/span")
            elif kind == "following":
                el = self.driver.find_element(By.XPATH, "//a[contains(@href,'following')]//span/span")
            else:
                return 0

            txt = el.get_attribute("title") or el.text
            txt = txt.replace(',', '').upper()

            num_match = re.search(r'[\d\.]+', txt)
            if not num_match:
                return 0

            num = float(num_match.group())

            if 'K' in txt:
                return int(num * 1000)
            elif 'M' in txt:
                return int(num * 1000000)
            return int(num)

        except Exception as e:
            logger.error(f"Stat error {kind}: {e}")
            return 0

    def analyze_profile(self, username):
        """YOUR EXACT analysis pipeline"""
        try:
            if not self.driver:
                if not self.init_driver():
                    return {"error": "Browser failed"}
            
            if not self.login():
                return {"error": "Login failed"}
            
            profile_url = f"https://www.instagram.com/{username}/"
            self.driver.get(profile_url)
            WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'header')))

            # Extract ALL features exactly like your notebook
            profile_pic = self.extract_profile_picture(username)
            
            # Username metrics
            uname_cleaned = re.sub(r'[^\w]', '', username)
            num_digits_un = sum(c.isdigit() for c in uname_cleaned)
            len_un = len(uname_cleaned)
            nums_per_len_username = round(num_digits_un / len_un, 2) if len_un else 0
            
            # Full name
            full_name = self.extract_full_name(username)
            words_fullname = len(full_name.split())
            num_digits_fn = sum(c.isdigit() for c in full_name)
            len_fn = len(full_name)
            nums_per_len_fullname = round(num_digits_fn / len_fn, 2) if len_fn else 0
            name_eq_username = 1 if full_name.replace(" ", "").lower() == username.lower() else 0
            
            # Description
            try:
                bio = self.driver.find_element(By.CSS_SELECTOR, "._ap3a._aaco._aacu._aacx._aad7._aade")
                desc_len = len(bio.get_attribute("innerText"))
            except NoSuchElementException:
                desc_len = 0
            
            # URL
            try:
                url_el = self.driver.find_element(By.XPATH, "//div[contains(@class,'x3nfvp2')]//a[@href]")
                has_url = 1 if url_el.text.strip() != "" else 0
            except NoSuchElementException:
                has_url = 0
            except Exception as e:
                logger.error(f"URL error: {str(e)}")
                has_url = 0
            
            # Private
            try:
                self.driver.find_element(By.XPATH, "//span[text()=\"This account is private\"]")
                is_private = 1
            except NoSuchElementException:
                is_private = 0
            
            # Stats
            num_posts = self.get_stat("posts")
            num_followers = self.get_stat("followers")
            num_follows = self.get_stat("following")

            # Prepare features for ML
            features = [
                profile_pic,
                nums_per_len_username,
                words_fullname,
                nums_per_len_fullname,
                name_eq_username,
                desc_len,
                has_url,
                is_private,
                num_posts,
                num_followers,
                num_follows
            ]
            
            # YOUR EXACT prediction logic
            sample_input = np.array([features])
            sample_input_scaled = self.scaler.transform(sample_input)
            prob = self.model.predict_proba(sample_input_scaled)[0]
            predicted_class = self.model.predict(sample_input_scaled)[0]
            authenticity_score = round(prob[0] * 10)
            
            verdict = "GENUINE" if predicted_class == 0 else "FAKE"

            return {
                "username": username,
                "analysis": {
                    "verdict": verdict,
                    "authenticity_score": authenticity_score,
                    "confidence": float(prob[0])
                },
                "features": {
                    'profile_pic': profile_pic,
                    'nums_per_len_username': nums_per_len_username,
                    'words_fullname': words_fullname,
                    'nums_per_len_fullname': nums_per_len_fullname,
                    'name_eq_username': name_eq_username,
                    'desc_len': desc_len,
                    'has_url': has_url,
                    'is_private': is_private,
                    'num_posts': num_posts,
                    'num_followers': num_followers,
                    'num_follows': num_follows
                },
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Analysis failed: {str(e)}")
            return {"error": f"Analysis failed: {str(e)}"}

# Initialize scraper
scraper = InstagramScraper()

@app.route('/')
def home():
    return jsonify({
        "message": "Instagram Profile Analyzer API - FULL SELENIUM AUTOMATION", 
        "status": "running",
        "endpoints": {
            "analyze": "POST /analyze"
        }
    })

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        
        if not username:
            return jsonify({"error": "Username required"}), 400
        
        result = scraper.analyze_profile(username)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
