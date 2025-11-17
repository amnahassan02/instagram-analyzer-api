from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.chrome.service import Service
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

class InstagramScraper:
    def __init__(self):
        self.driver = None
        self.model = None
        self.scaler = None
        self.expected_features = None
        self.setup_driver()
        self.load_model()
    
    def setup_driver(self):
        """Setup Chrome driver for Railway"""
        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            # Set user agent
            ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            chrome_options.add_argument(f"--user-agent={ua}")
            
            # For Railway deployment
            chrome_options.binary_location = "/usr/bin/google-chrome"
            
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.get("https://www.instagram.com/")
            logger.info("Chrome driver initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize driver: {str(e)}")
            raise

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

    def login(self):
        """Login to Instagram"""
        try:
            time.sleep(3)
            
            # Get credentials from environment
            instagram_username = os.getenv('INSTAGRAM_USERNAME')
            instagram_password = os.getenv('INSTAGRAM_PASSWORD')
            
            if not instagram_username or not instagram_password:
                raise Exception("Instagram credentials not found")
            
            # Find login elements
            username_field = WebDriverWait(self.driver, 15).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input[name='username']")))
            password_field = WebDriverWait(self.driver, 15).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input[name='password']")))

            username_field.clear()
            username_field.send_keys(instagram_username)
            time.sleep(1)
            password_field.clear()
            password_field.send_keys(instagram_password)
            password_field.send_keys(Keys.ENTER)
            
            logger.info("Login submitted")
            time.sleep(5)

            # Handle pop-ups
            try:
                not_now_btn = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Not Now')]")))
                not_now_btn.click()
                logger.info("Clicked 'Not Now'")
                time.sleep(2)
            except TimeoutException:
                logger.info("No pop-up found")
                
            return True
            
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            return False

    def extract_features(self, username):
        """Extract all features from profile"""
        try:
            profile_url = f"https://www.instagram.com/{username}/"
            self.driver.get(profile_url)
            
            # Wait for profile to load
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, 'header')))
            
            features = {}
            
            # 1. Profile Picture
            features['profile_pic'] = self.check_profile_picture()
            
            # 2. Username metrics
            uname_cleaned = re.sub(r'[^\w]', '', username)
            num_digits_un = sum(c.isdigit() for c in uname_cleaned)
            len_un = len(uname_cleaned)
            features['nums_per_len_username'] = round(num_digits_un / len_un, 2) if len_un else 0
            
            # 3-4. Full Name
            full_name = self.get_full_name(username, uname_cleaned)
            words_fullname = len(full_name.split())
            num_digits_fn = sum(c.isdigit() for c in full_name)
            len_fn = len(full_name)
            features['words_fullname'] = words_fullname
            features['nums_per_len_fullname'] = round(num_digits_fn / len_fn, 2) if len_fn else 0
            
            # 5. Name equals username
            features['name_eq_username'] = 1 if full_name.replace(" ", "").lower() == username.lower() else 0
            
            # 6. Description length
            features['desc_len'] = self.get_description_length()
            
            # 7. External URL
            features['has_url'] = self.check_external_url()
            
            # 8. Private account
            features['is_private'] = self.check_private()
            
            # 9-11. Stats
            stats = self.get_stats()
            features.update(stats)
            
            return features
            
        except Exception as e:
            logger.error(f"Feature extraction failed: {str(e)}")
            raise

    def check_profile_picture(self):
        """Check if profile has custom picture"""
        try:
            pic = self.driver.find_element(By.CSS_SELECTOR, "img[alt*='profile picture']")
            src = pic.get_attribute('src')
            return 0 if 'anonymous_profile_pic' in src else 1
        except:
            return 0

    def get_full_name(self, username, uname_cleaned):
        """Extract and clean full name"""
        try:
            selectors = [
                "//header//h1",
                "//header//div[2]//span", 
                "//header//span",
                "//header//div[contains(@class, '_aacl')]"
            ]
            
            for selector in selectors:
                try:
                    element = self.driver.find_element(By.XPATH, selector)
                    text = element.text.strip()
                    if text and len(text) > 1 and "posts" not in text.lower():
                        # Clean the name
                        if uname_cleaned.lower() in text.lower():
                            text = re.sub(uname_cleaned, '', text, flags=re.IGNORECASE).strip()
                        # Limit to 2 words
                        words = text.split()
                        return " ".join(words[:2]) if len(words) > 2 else text
                except:
                    continue
            return ""
        except:
            return ""

    def get_description_length(self):
        """Get bio description length"""
        try:
            bio = self.driver.find_element(By.CSS_SELECTOR, "._ap3a, ._aacu, ._aad6")
            return len(bio.text)
        except:
            return 0

    def check_external_url(self):
        """Check for external URL in bio"""
        try:
            url_elements = self.driver.find_elements(By.XPATH, "//div[contains(@class, '_aacx')]//a[@href]")
            for element in url_elements:
                if element.text.strip():
                    return 1
            return 0
        except:
            return 0

    def check_private(self):
        """Check if account is private"""
        try:
            self.driver.find_element(By.XPATH, "//h2[contains(text(), 'This Account is Private')]")
            return 1
        except:
            return 0

    def get_stats(self):
        """Extract posts, followers, following counts"""
        def parse_stat(text):
            text = text.upper().replace(',', '')
            if 'K' in text:
                return int(float(text.replace('K', '')) * 1000)
            elif 'M' in text:
                return int(float(text.replace('M', '')) * 1000000)
            else:
                return int(text) if text.isdigit() else 0

        stats = {'num_posts': 0, 'num_followers': 0, 'num_follows': 0}
        
        try:
            # Find all stat elements
            stat_elements = self.driver.find_elements(By.XPATH, "//header//section//ul//li//span//span")
            
            if len(stat_elements) >= 3:
                stats['num_posts'] = parse_stat(stat_elements[0].text)
                stats['num_followers'] = parse_stat(stat_elements[1].text)
                stats['num_follows'] = parse_stat(stat_elements[2].text)
                
        except Exception as e:
            logger.error(f"Error parsing stats: {e}")
            
        return stats

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
                'features': features
            }
            
        except Exception as e:
            logger.error(f"Prediction failed: {str(e)}")
            raise

    def close(self):
        """Close driver"""
        if self.driver:
            self.driver.quit()

# Initialize scraper
scraper = InstagramScraper()

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
        
        logger.info(f"Analyzing: {username}")
        
        # Login if needed
        if not scraper.login():
            return jsonify({"error": "Instagram login failed"}), 500
        
        # Extract features and predict
        features = scraper.extract_features(username)
        result = scraper.predict(features)
        
        response = {
            "username": username,
            "analysis": {
                "is_fake": result['is_fake'],
                "authenticity_score": result['authenticity_score'],
                "confidence": result['confidence'],
                "verdict": "FAKE" if result['is_fake'] else "GENUINE"
            },
            "features": features,
            "timestamp": datetime.now().isoformat()
        }
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Analysis error: {str(e)}")
        return jsonify({"error": f"Analysis failed: {str(e)}"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)