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
        self.load_model()
    
    def load_model(self):
        """Load ML model and scaler"""
        try:
            self.model = joblib.load('random_forest_model.joblib')
            self.scaler = joblib.load('scaler.joblib')
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
            
            logger.info("Chrome driver initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize driver: {str(e)}")
            return False

    def analyze_profile(self, username):
        """Main analysis function"""
        try:
            # Initialize driver if not already done
            if not self.driver:
                if not self.init_driver():
                    return {"error": "Failed to initialize browser"}
            
            # Navigate to profile
            profile_url = f"https://www.instagram.com/{username}/"
            self.driver.get(profile_url)
            time.sleep(5)
            
            # Check if profile exists
            if "Sorry, this page isn't available." in self.driver.page_source:
                return {"error": "Profile not found"}
            
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
            # 1. Profile Picture - just check if any image exists in header
            try:
                header = self.driver.find_element(By.TAG_NAME, "header")
                images = header.find_elements(By.TAG_NAME, "img")
                features['profile_pic'] = 1 if len(images) > 0 else 0
            except:
                features['profile_pic'] = 0

            # 2. Username metrics
            uname_cleaned = re.sub(r'[^\w]', '', username)
            num_digits_un = sum(c.isdigit() for c in uname_cleaned)
            len_un = len(uname_cleaned)
            features['nums_per_len_username'] = round(num_digits_un / len_un, 2) if len_un else 0

            # 3-5. Full Name - simplified
            full_name = ""
            try:
                # Just look for any span text that might be a name
                spans = self.driver.find_elements(By.TAG_NAME, "span")
                for span in spans:
                    text = span.text.strip()
                    if text and len(text) > 1 and len(text) < 50 and text != username:
                        full_name = text
                        break
            except:
                pass

            features['words_fullname'] = len(full_name.split())
            num_digits_fn = sum(c.isdigit() for c in full_name)
            len_fn = len(full_name)
            features['nums_per_len_fullname'] = round(num_digits_fn / len_fn, 2) if len_fn else 0
            features['name_eq_username'] = 1 if full_name.replace(" ", "").lower() == username.lower() else 0

            # 6. Description length - simplified
            try:
                # Count all text in header as description
                header = self.driver.find_element(By.TAG_NAME, "header")
                features['desc_len'] = len(header.text)
            except:
                features['desc_len'] = 0

            # 7. External URL - simplified
            try:
                links = self.driver.find_elements(By.TAG_NAME, "a")
                for link in links:
                    href = link.get_attribute('href')
                    if href and 'instagram.com' not in href:
                        features['has_url'] = 1
                        break
            except:
                features['has_url'] = 0

            # 8. Private account
            try:
                page_text = self.driver.page_source
                features['is_private'] = 1 if 'This account is private' in page_text else 0
            except:
                features['is_private'] = 0

            # 9-11. Stats - look for numbers in the page
            try:
                # Look for common patterns
                page_text = self.driver.page_source
                
                # Posts pattern
                posts_match = re.search(r'(\d+[KM]?)\s*posts?', page_text, re.IGNORECASE)
                if posts_match:
                    features['num_posts'] = self.parse_count(posts_match.group(1))
                
                # Followers pattern  
                followers_match = re.search(r'(\d+[KM]?)\s*followers', page_text, re.IGNORECASE)
                if followers_match:
                    features['num_followers'] = self.parse_count(followers_match.group(1))
                
                # Following pattern
                following_match = re.search(r'(\d+[KM]?)\s*following', page_text, re.IGNORECASE)
                if following_match:
                    features['num_follows'] = self.parse_count(following_match.group(1))
                    
            except Exception as e:
                logger.error(f"Stats parsing error: {e}")

            return features
            
        except Exception as e:
            logger.error(f"Feature extraction error: {str(e)}")
            return features

    def parse_count(self, text):
        """Parse counts like 1.2K, 5.5M"""
        try:
            text = text.upper().replace(',', '').replace(' ', '')
            
            # Extract numbers
            numbers = re.findall(r'[\d\.]+', text)
            if not numbers:
                return 0
                
            num = float(numbers[0])
            
            if 'K' in text:
                return int(num * 1000)
            elif 'M' in text:
                return int(num * 1000000)
            else:
                return int(num)
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
