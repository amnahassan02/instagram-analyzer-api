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
            chrome_options.add_argument("--headless=new")
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
        """Login to Instagram"""
        try:
            self.driver.get("https://www.instagram.com/accounts/login/")
            time.sleep(3)
            
            username = os.getenv('INSTAGRAM_USERNAME')
            password = os.getenv('INSTAGRAM_PASSWORD')
            
            if not username or not password:
                raise Exception("Instagram credentials not found in environment")
            
            # Find login fields
            username_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, "username")))
            password_field = self.driver.find_element(By.NAME, "password")
            
            username_field.send_keys(username)
            password_field.send_keys(password)
            password_field.send_keys(Keys.ENTER)
            
            logger.info("Login submitted")
            time.sleep(5)
            
            # Handle pop-ups
            try:
                not_now_btn = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Not Now')]")))
                not_now_btn.click()
                time.sleep(2)
            except TimeoutException:
                pass
                
            return True
            
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            return False

    def analyze_profile(self, username):
        """Main analysis function"""
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
            time.sleep(3)
            
            # Extract features
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
        """Extract profile features"""
        features = {
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
        
        try:
            # 1. Profile Picture
            try:
                pic = self.driver.find_element(By.CSS_SELECTOR, "img[src*='instagram']")
                src = pic.get_attribute('src')
                features['profile_pic'] = 0 if 'anonymous' in src.lower() else 1
            except:
                features['profile_pic'] = 0

            # 2. Username metrics
            uname_cleaned = re.sub(r'[^\w]', '', username)
            num_digits_un = sum(c.isdigit() for c in uname_cleaned)
            len_un = len(uname_cleaned)
            features['nums_per_len_username'] = round(num_digits_un / len_un, 2) if len_un else 0

            # 3-5. Full Name
            full_name = ""
            try:
                # Try multiple selectors for full name
                name_selectors = [
                    "//header//h1",
                    "//header//section//div//span",
                    "//header//div[2]//span"
                ]
                
                for selector in name_selectors:
                    try:
                        element = self.driver.find_element(By.XPATH, selector)
                        text = element.text.strip()
                        if text and len(text) > 1 and len(text) < 50:
                            full_name = text
                            break
                    except:
                        continue
                
                # Clean name
                if uname_cleaned.lower() in full_name.lower():
                    full_name = re.sub(uname_cleaned, '', full_name, flags=re.IGNORECASE).strip()
                
                # Limit to 2 words
                words = full_name.split()
                if len(words) > 2:
                    full_name = " ".join(words[:2])
                    
            except:
                full_name = ""

            features['words_fullname'] = len(full_name.split())
            num_digits_fn = sum(c.isdigit() for c in full_name)
            len_fn = len(full_name)
            features['nums_per_len_fullname'] = round(num_digits_fn / len_fn, 2) if len_fn else 0
            features['name_eq_username'] = 1 if full_name.replace(" ", "").lower() == username.lower() else 0

            # 6. Description length
            try:
                bio_elements = self.driver.find_elements(By.XPATH, "//header//section//div")
                for element in bio_elements:
                    text = element.text
                    if text and len(text) > 10:  # Likely a bio
                        features['desc_len'] = len(text)
                        break
            except:
                features['desc_len'] = 0

            # 7. External URL
            try:
                links = self.driver.find_elements(By.XPATH, "//header//a[@href]")
                for link in links:
                    href = link.get_attribute('href')
                    text = link.text
                    if href and text and 'instagram.com' not in href:
                        features['has_url'] = 1
                        break
            except:
                features['has_url'] = 0

            # 8. Private account
            try:
                private_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'private') or contains(text(), 'Private')]")
                features['is_private'] = 1 if private_elements else 0
            except:
                features['is_private'] = 0

            # 9-11. Stats (simplified parsing)
            try:
                stat_elements = self.driver.find_elements(By.XPATH, "//header//section//ul//li//span//span")
                if len(stat_elements) >= 3:
                    features['num_posts'] = self.parse_count(stat_elements[0].text)
                    features['num_followers'] = self.parse_count(stat_elements[1].text)
                    features['num_follows'] = self.parse_count(stat_elements[2].text)
            except:
                pass

            return features
            
        except Exception as e:
            logger.error(f"Feature extraction error: {str(e)}")
            return features

    def parse_count(self, text):
        """Parse follower counts like 1.2K, 5.5M"""
        try:
            text = text.upper().replace(',', '')
            if 'K' in text:
                return int(float(text.replace('K', '')) * 1000)
            elif 'M' in text:
                return int(float(text.replace('M', '')) * 1000000)
            else:
                return int(text) if text.replace('.', '').isdigit() else 0
        except:
            return 0

    def predict(self, features):
        """Make prediction using ML model"""
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

    def close(self):
        """Close driver"""
        if self.driver:
            self.driver.quit()

# Initialize analyzer
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

@app.before_request
def before_request():
    """Initialize driver before first request if needed"""
    if not analyzer.driver:
        analyzer.init_driver()

@app.teardown_appcontext
def close_driver(exception=None):
    """Close driver when app shuts down"""
    analyzer.close()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
