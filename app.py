from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, TimeoutException
import os
import time
import re
import joblib
import numpy as np
from datetime import datetime
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

class InstagramAnalyzer:
    def __init__(self):
        self.driver = None
        self.model = None
        self.scaler = None
        self.expected_features = None
        self.load_model()
    
    def load_model(self):
        """Load ML model and scaler"""
        try:
            self.model = joblib.load('random_forest_model.joblib')
            self.scaler = joblib.load('scaler.joblib')
            with open('feature_names.txt', 'r') as f:
                self.expected_features = f.read().split(',')
            logger.info("ML model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load ML model: {str(e)}")
            raise

    def init_driver(self):
        """Initialize Chrome driver"""
        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            
            # Anti-detection
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            # Set user agent
            ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            chrome_options.add_argument(f"user-agent={ua}")
            
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            logger.info("Chrome driver initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize driver: {str(e)}")
            return False

    def login(self):
        """Login to Instagram - YOUR ORIGINAL LOGIC"""
        try:
            self.driver.get("https://www.instagram.com/")
            time.sleep(3)
            
            username = os.getenv('INSTAGRAM_USERNAME')
            password = os.getenv('INSTAGRAM_PASSWORD')
            
            if not username or not password:
                raise Exception("Instagram credentials not found in environment")
            
            # Find login fields - YOUR ORIGINAL SELECTORS
            username_field = WebDriverWait(self.driver, 15).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input[name='username']")))
            password_field = WebDriverWait(self.driver, 15).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input[name='password']")))

            username_field.clear()
            username_field.send_keys(username)
            time.sleep(1)
            password_field.clear()
            password_field.send_keys(password)
            password_field.send_keys(Keys.ENTER)
            
            logger.info("Login submitted")
            time.sleep(5)

            # Handle pop-ups - YOUR ORIGINAL LOGIC
            try:
                not_now_btn = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Not Now')]")))
                not_now_btn.click()
                logger.info("Clicked 'Not Now' on pop-up")
                time.sleep(2)
            except TimeoutException:
                logger.info("No pop-up found")
                
            return True
            
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            return False

    def analyze_profile(self, username):
        """Main analysis function - KEEPS YOUR ORIGINAL SCRAPING LOGIC"""
        try:
            # Initialize driver if not already done
            if not self.driver:
                if not self.init_driver():
                    return {"error": "Failed to initialize browser"}
            
            # Login if needed
            if not self.login():
                return {"error": "Failed to login to Instagram"}
            
            # Navigate to profile
            profile_url = f"https://www.instagram.com/{username}/"
            self.driver.get(profile_url)
            
            # Wait for profile to load - YOUR ORIGINAL LOGIC
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, 'header')))
            
            # Extract features using YOUR original logic
            features = self.extract_features(username)
            
            # Make prediction
            prediction = self.predict(features)
            
            return {
                "username": username,
                "analysis": prediction,
                "features": features,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Analysis failed: {str(e)}")
            return {"error": f"Analysis failed: {str(e)}"}

    def extract_features(self, username):
        """YOUR ORIGINAL FEATURE EXTRACTION LOGIC"""
        features = {}
        
        try:
            # 1. Profile Picture - YOUR ORIGINAL LOGIC
            try:
                pic = self.driver.find_element(By.CSS_SELECTOR, "img[alt$=\"'s profile picture\"]")
                src = pic.get_attribute('src')
                if 'ig_cache_key=YW5vbnltb3VzX3Byb2ZpbGVfcGlj' in src:
                    features['profile_pic'] = 0  # Default picture
                else:
                    features['profile_pic'] = 1  # Custom picture
            except NoSuchElementException:
                features['profile_pic'] = 0

            # 2. Username metrics - YOUR ORIGINAL LOGIC
            uname_cleaned = re.sub(r'[^\w]', '', username)
            num_digits_un = sum(c.isdigit() for c in uname_cleaned)
            len_un = len(uname_cleaned)
            features['nums_per_len_username'] = round(num_digits_un / len_un, 2) if len_un else 0

            # 3-5. Full Name Analysis - YOUR ORIGINAL LOGIC
            full_name = ""
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
                    if uname_cleaned and uname_cleaned.lower() in full_name_raw.lower():
                        pattern = r'\s*' + re.escape(uname_cleaned) + r'\s*$'
                        full_name = re.sub(pattern, '', full_name_raw, flags=re.IGNORECASE).strip()
                    else:
                        full_name = full_name_raw
                    
                    if len(full_name.split()) > 2:
                        full_name = " ".join(full_name.split()[:2])
                else:
                    full_name = ""
                    
            except Exception as e:
                logger.error(f"Full name extraction error: {e}")
                full_name = ""

            features['words_fullname'] = len(full_name.split())
            num_digits_fn = sum(c.isdigit() for c in full_name)
            len_fn = len(full_name)
            features['nums_per_len_fullname'] = round(num_digits_fn / len_fn, 2) if len_fn else 0
            features['name_eq_username'] = 1 if full_name.replace(" ", "").lower() == username.lower() else 0

            # 6. Description length - YOUR ORIGINAL LOGIC
            try:
                bio = self.driver.find_element(By.CSS_SELECTOR, "._ap3a._aaco._aacu._aacx._aad7._aade")
                description = bio.get_attribute("innerText")
                features['desc_len'] = len(description)
            except NoSuchElementException:
                features['desc_len'] = 0

            # 7. External URL - YOUR ORIGINAL LOGIC
            try:
                url_el = self.driver.find_element(By.XPATH, "//div[contains(@class,'x3nfvp2')]//a[@href]")
                features['has_url'] = 1 if url_el.text.strip() != "" else 0
            except NoSuchElementException:
                features['has_url'] = 0

            # 8. Private account - YOUR ORIGINAL LOGIC
            try:
                self.driver.find_element(By.XPATH, "//span[text()=\"This account is private\"]")
                features['is_private'] = 1
            except NoSuchElementException:
                features['is_private'] = 0

            # 9-11. Posts, Followers, Following - YOUR ORIGINAL LOGIC
            def get_stat(kind):
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
                    logger.error(f"Error parsing {kind}: {e}")
                    return 0

            features['num_posts'] = get_stat("posts")
            features['num_followers'] = get_stat("followers")
            features['num_follows'] = get_stat("following")

            return features
            
        except Exception as e:
            logger.error(f"Feature extraction error: {str(e)}")
            # Return default features on error
            return {
                'profile_pic': 0,
                'nums_per_len_username': 0,
                'words_fullname': 0,
                'nums_per_len_fullname': 0,
                'name_eq_username': 0,
                'desc_len': 0,
                'has_url': 0,
                'is_private': 0,
                'num_posts': 0,
                'num_followers': 0,
                'num_follows': 0
            }

    def predict(self, features):
        """Make prediction using ML model - YOUR ORIGINAL LOGIC"""
        try:
            feature_list = [
                features['profile_pic'],
                features['nums_per_len_username'],
                features['words_fullname'],
                features['nums_per_len_fullname'],
                features['name_eq_username'],
                features['desc_len'],
                features['has_url'],
                features['is_private'],
                features['num_posts'],
                features['num_followers'],
                features['num_follows']
            ]
            
            sample_input = np.array([feature_list])
            sample_scaled = self.scaler.transform(sample_input)
            
            prob = self.model.predict_proba(sample_scaled)[0]
            predicted_class = self.model.predict(sample_scaled)[0]
            score = round(prob[0] * 10)
            
            return {
                'is_fake': bool(predicted_class),
                'authenticity_score': score,
                'confidence': float(prob[0]),
                'verdict': "FAKE" if predicted_class else "GENUINE"
            }
            
        except Exception as e:
            logger.error(f"Prediction failed: {str(e)}")
            return {
                'is_fake': True,
                'authenticity_score': 0,
                'confidence': 0.0,
                'verdict': "ERROR"
            }

# Global analyzer instance
analyzer = InstagramAnalyzer()

@app.route('/')
def home():
    return jsonify({
        "message": "Instagram Profile Analyzer API", 
        "status": "running",
        "endpoints": {
            "analyze": "POST /analyze",
            "health": "GET /health"
        }
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.route('/analyze', methods=['POST'])
def analyze():
    """Main analysis endpoint"""
    try:
        data = request.get_json()
        
        if not data or 'username' not in data:
            return jsonify({"error": "Username is required"}), 400
        
        username = data['username'].strip()
        if not username:
            return jsonify({"error": "Username cannot be empty"}), 400
        
        logger.info(f"Analyzing profile: {username}")
        
        result = analyzer.analyze_profile(username)
        
        if 'error' in result:
            return jsonify(result), 500
            
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Analysis error: {str(e)}")
        return jsonify({"error": f"Analysis failed: {str(e)}"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
