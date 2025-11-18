from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import NoSuchElementException, TimeoutException
import os
import time
import re
import base64
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
        self.model_loaded = False
        self.load_model()
    
    def load_model(self):
        """Load ML model and scaler"""
        try:
            logger.info("Loading ML model...")
            # NOTE: These files (random_forest_model.joblib, scaler.joblib, feature_names.txt) 
            # must be present in the root directory for this to succeed.
            self.model = joblib.load('random_forest_model.joblib')
            self.scaler = joblib.load('scaler.joblib')
            with open('feature_names.txt', 'r') as f:
                self.expected_features = f.read().split(',')
            logger.info("ML model loaded successfully")
            self.model_loaded = True
        except Exception as e:
            logger.error(f"Failed to load ML model: {str(e)}")
            self.model_loaded = False

    def init_driver(self):
        """Initialize Chrome driver with automatic ChromeDriver management and path correction."""
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

            # --- VITAL CORRECTION ---
            # Use webdriver-manager to automatically handle ChromeDriver version
            # Use Service object path installation approach for better path resolution
            try:
                # This should resolve to the path of the executable.
                driver_path = ChromeDriverManager().install()
            except Exception as e:
                logger.error(f"WDM installation failed, trying local path: {e}")
                # Fallback path if WDM fails, but WDM is preferred in this setup
                driver_path = "/usr/bin/chromedriver" 
            
            # --- PATH CORRECTION LOGIC ---
            # 1. Correct the path if it points to the THIRD_PARTY_NOTICES.chromedriver file
            if 'THIRD_PARTY_NOTICES.chromedriver' in driver_path:
                correct_path = driver_path.replace('THIRD_PARTY_NOTICES.chromedriver', 'chromedriver')
            # 2. If WDM returns the directory path, append 'chromedriver'
            elif os.path.isdir(driver_path) and not driver_path.endswith('chromedriver'): 
                 correct_path = os.path.join(driver_path, 'chromedriver')
            else:
                 correct_path = driver_path
                 
            logger.info(f"Using ChromeDriver path: {correct_path}")
                 
            # Ensure the corrected path is executable and exists
            if not os.path.exists(correct_path):
                 raise FileNotFoundError(f"Corrected chromedriver path not found: {correct_path}")
                 
            # Explicitly set permissions, which is often required in Docker containers
            os.chmod(correct_path, 0o755) 
            
            service = Service(correct_path)
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            # --- END CORRECTION ---
            
            self.driver.get("https://www.instagram.com/")
            logger.info("Chrome driver initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize driver: {str(e)}")
            return False

    def login(self):
        """Login to Instagram"""
        try:
            time.sleep(2)
            
            username = os.getenv('INSTAGRAM_USERNAME')
            password = os.getenv('INSTAGRAM_PASSWORD')
            
            if not username or not password:
                logger.warning("Instagram credentials not found, attempting to bypass login.")
                return True

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
            logger.info("Login submitted.")
            time.sleep(5)

            try:
                # Handle "Save Your Login Info?" pop-up
                not_now_button = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Not Now')]"))
                )
                not_now_button.click()
                logger.info("Clicked 'Not Now' on 'Save Login Info' pop-up.")
                time.sleep(2)
            except TimeoutException:
                pass
                
            return True
            
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            return False

    def extract_profile_picture(self, username):
        """Extracts profile picture status and base64 data."""
        try:
            try:
                 # Attempt to find the profile picture element
                 pic = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "img[alt$=\"'s profile picture\"], header img[alt*='profile']"))
                )
            except TimeoutException:
                 try:
                     pic = self.driver.find_element(By.CSS_SELECTOR, "header img[alt*='profile']")
                 except NoSuchElementException:
                     pic = self.driver.find_element(By.CSS_SELECTOR, "._aadg img[alt*='profile']")

            src = pic.get_attribute('src')

            js_script = """
                var img = arguments[0];
                var canvas = document.createElement('canvas');
                canvas.width = img.naturalWidth || img.clientWidth;
                canvas.height = img.naturalHeight || img.clientHeight;
                if(canvas.width === 0 || canvas.height === 0) return null;
                canvas.getContext('2d').drawImage(img, 0, 0);
                return canvas.toDataURL('image/jpeg');
            """
            base64_data = self.driver.execute_script(js_script, pic)
            
            if not base64_data:
                 raise ValueError("Could not extract image data via canvas.")

            base64_content = base64_data.split(',')[1]

            # Check if it's the default Instagram placeholder
            if 'ig_cache_key=YW5vbnltb3VzX3Byb2ZpbGVfcGlj' in src or len(base64_content) < 5000:
                profile_pic = 0
            else:
                profile_pic = 1

            return {
                'profile_pic': profile_pic,
                'image_base64': base64_data,
                'image_data': base64_content
            }
                
        except NoSuchElementException:
            logger.info("Profile picture element not found.")
            return {'profile_pic': 0, 'image_base64': None, 'image_data': None}
        except Exception as e:
            logger.error(f"Error during picture extraction: {str(e)}")
            return {'profile_pic': 0, 'image_base64': None, 'image_data': None}

    def extract_features(self, username):
        """Extracts all necessary features for the ML model."""
        features = {}
        
        # 1) Profile Picture
        pic_result = self.extract_profile_picture(username)
        features['profile_pic'] = pic_result['profile_pic']
        
        # 2) username metrics
        uname_raw = username 
        uname_cleaned = re.sub(r'[^\w]', '', uname_raw)
        num_digits_un = sum(c.isdigit() for c in uname_cleaned)
        len_un = len(uname_cleaned)
        features['nums_per_len_username'] = round(num_digits_un / len_un, 2) if len_un else 0
        
        # 3–5) full name metrics (words, digits/length, name == username)
        full_name = ""
        try:
            # Attempt to find the displayed profile name
            selectors = [
                "//header//div[2]//span/div[1]/span", 
                "//header//h1",  
                "//header//div[contains(@class, '_aacx')]//span",
                "//header//div[contains(@class, '_aacl')]",
                "//header//div[contains(@class, '_aac')]//span[1]",
            ]
            
            for selector in selectors:
                try:
                    element = self.driver.find_element(By.XPATH, selector)
                    text = element.text.strip()
                    
                    if (text and 
                        not text.startswith('@') and 
                        not text.startswith('#') and
                        "posts" not in text.lower() and
                        1 < len(text) < 50):
                        
                        full_name = text
                        
                        # Apply maximum two words rule
                        if len(full_name.split()) > 2:
                            full_name = " ".join(full_name.split()[:2])
                            
                        break
                        
                except NoSuchElementException:
                    continue
            
        except Exception as e:
            logger.error(f"Error finding profile name: {e}")

        features['words_fullname'] = len(full_name.split())
        num_digits_fn = sum(c.isdigit() for c in full_name)
        len_fn = len(full_name)
        features['nums_per_len_fullname'] = round(num_digits_fn / len_fn, 2) if len_fn else 0
        
        features['name_eq_username'] = 1 if full_name.replace(" ", "").lower() == uname_raw.lower() else 0
        
        # 6) description length
        try:
            bio = self.driver.find_element(By.CSS_SELECTOR, "._ap3a._aaco._aacu._aacx._aad7._aade")
            description = bio.get_attribute("innerText")
            features['desc_len'] = len(description)
        except NoSuchElementException:
            features['desc_len'] = 0
        
        # 7) external URL present?
        try:
            url_el = self.driver.find_element(By.XPATH, "//div[contains(@class,'x3nfvp2')]//a[@href]")
            features['has_url'] = 1 if url_el.text.strip() != "" else 0
        except NoSuchElementException:
            features['has_url'] = 0
        except Exception as e:
            logger.error(f"URL detection error: {str(e)}")
            features['has_url'] = 0
        
        # 8) private account?
        try:
            self.driver.find_element(By.XPATH, "//span[text()=\"This account is private\"]")
            features['is_private'] = 1
        except NoSuchElementException:
            features['is_private'] = 0
        
        # 9–11) posts, followers, following
        def get_stat(kind):
            try:
                if kind == "posts":
                    el = self.driver.find_element(By.XPATH, "//div[span[contains(text(),'posts')]]//span/span | //li[contains(.,'posts')]//span/span")
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

    def predict(self, features):
        """Makes a prediction using the loaded ML model."""
        if not self.model_loaded:
            return {
                'is_fake': False,
                'authenticity_score': 5,
                'confidence': 0.5,
                'verdict': "MODEL_NOT_LOADED"
            }
        
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
            
            if len(feature_list) != len(self.expected_features):
                raise ValueError("Mismatch in number of features!")
            
            sample_input = np.array([feature_list])
            sample_input_scaled = self.scaler.transform(sample_input)
            
            prob = self.model.predict_proba(sample_input_scaled)[0]
            predicted_class = self.model.predict(sample_input_scaled)[0]
            
            authenticity_score = round(prob[0] * 10)
            
            verdict = "GENUINE" if predicted_class == 0 else "FAKE"
            
            return {
                'is_fake': bool(predicted_class),
                'authenticity_score': authenticity_score,
                'confidence': float(prob[0]),
                'verdict': verdict
            }
            
        except Exception as e:
            logger.error(f"Prediction failed: {str(e)}")
            return {
                'is_fake': False,
                'authenticity_score': 5,
                'confidence': 0.5,
                'verdict': "PREDICTION_ERROR"
            }

    def analyze_profile(self, username):
        """Main analysis function"""
        try:
            if not self.driver:
                if not self.init_driver():
                    return {"error": "Failed to initialize browser"}
            
            if not self.login():
                return {"error": "Failed to login to Instagram"}
            
            profile_url = f"https://www.instagram.com/{username}/"
            self.driver.get(profile_url)
            
            WebDriverWait(self.driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, 'header')))
            
            pic_result = self.extract_profile_picture(username)
            features = self.extract_features(username)
            prediction = self.predict(features)
            
            return {
                "username": username,
                "analysis": prediction,
                "features": features,
                "profile_picture": {
                    "has_custom_picture": bool(pic_result['profile_pic']),
                    "image_base64": pic_result['image_base64']
                },
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Analysis failed: {str(e)}")
            return {"error": f"Analysis failed: {str(e)}"}
        finally:
            if self.driver:
                self.driver.quit()
                self.driver = None

analyzer = InstagramAnalyzer()

@app.route('/')
def home():
    return jsonify({
        "message": "Instagram Profile Analyzer API - FIXED Version", 
        "status": "running",
        "model_loaded": analyzer.model_loaded,
        "endpoints": {
            "analyze": "POST /analyze",
            "health": "GET /health"
        }
    })

@app.route('/health')
def health():
    return jsonify({
        "status": "healthy", 
        "model_loaded": analyzer.model_loaded,
        "timestamp": datetime.now().isoformat()
    })

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
            # Propagate the 500 error if analysis fails
            return jsonify(result), 500
            
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Analysis error: {str(e)}")
        return jsonify({"error": f"Analysis failed: {str(e)}"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
