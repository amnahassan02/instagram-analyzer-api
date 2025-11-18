from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import os
import time
import re
import base64
import joblib
import numpy as np

app = Flask(__name__)

def create_driver():
    """Create Chrome driver with basic options"""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    return webdriver.Chrome(options=options)

def login_instagram(driver):
    """Login to Instagram"""
    driver.get("https://www.instagram.com/accounts/login/")
    time.sleep(3)
    
    username = os.getenv('INSTAGRAM_USERNAME')
    password = os.getenv('INSTAGRAM_PASSWORD')
    
    username_field = driver.find_element(By.NAME, "username")
    password_field = driver.find_element(By.NAME, "password")
    
    username_field.send_keys(username)
    password_field.send_keys(password)
    password_field.send_keys(Keys.ENTER)
    time.sleep(5)
    
    # Handle popup
    try:
        not_now_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Not Now')]"))
        )
        not_now_btn.click()
        time.sleep(2)
    except:
        pass
    
    return True

def analyze_profile(username):
    """Main analysis function"""
    driver = None
    try:
        driver = create_driver()
        
        # Login
        if not login_instagram(driver):
            return {"error": "Login failed"}
        
        # Navigate to profile
        driver.get(f"https://www.instagram.com/{username}/")
        time.sleep(3)
        
        # Extract basic features (simplified)
        features = {}
        
        # Profile picture
        try:
            img = driver.find_element(By.CSS_SELECTOR, "img[src*='instagram']")
            src = img.get_attribute('src')
            features['profile_pic'] = 0 if 'anonymous' in src else 1
        except:
            features['profile_pic'] = 0
        
        # Username metrics
        cleaned_username = re.sub(r'[^\w]', '', username)
        num_digits = sum(c.isdigit() for c in cleaned_username)
        features['nums_per_len_username'] = round(num_digits / len(cleaned_username), 2) if cleaned_username else 0
        
        # Full name
        try:
            name_element = driver.find_element(By.XPATH, "//h1 | //header//span")
            full_name = name_element.text
            features['words_fullname'] = len(full_name.split())
            features['nums_per_len_fullname'] = 0
            features['name_eq_username'] = 1 if full_name.replace(" ", "").lower() == username.lower() else 0
        except:
            features['words_fullname'] = 0
            features['nums_per_len_fullname'] = 0
            features['name_eq_username'] = 0
        
        # Other features (simplified)
        features['desc_len'] = 0
        features['has_url'] = 0
        features['is_private'] = 0
        features['num_posts'] = 0
        features['num_followers'] = 0
        features['num_follows'] = 0
        
        # Try to get stats
        try:
            stats = driver.find_elements(By.XPATH, "//header//ul//li")
            if len(stats) >= 3:
                features['num_posts'] = parse_count(stats[0].text)
                features['num_followers'] = parse_count(stats[1].text)
                features['num_follows'] = parse_count(stats[2].text)
        except:
            pass
        
        # Make prediction if model exists
        try:
            model = joblib.load('random_forest_model.joblib')
            scaler = joblib.load('scaler.joblib')
            
            feature_list = [features[k] for k in sorted(features.keys())]
            sample_scaled = scaler.transform([feature_list])
            prob = model.predict_proba(sample_scaled)[0]
            score = round(prob[0] * 10)
            verdict = "GENUINE" if model.predict(sample_scaled)[0] == 0 else "FAKE"
            
            return {
                "username": username,
                "analysis": {"verdict": verdict, "score": score},
                "features": features
            }
        except:
            return {
                "username": username,
                "analysis": {"verdict": "MODEL_UNAVAILABLE", "score": 5},
                "features": features
            }
            
    except Exception as e:
        return {"error": str(e)}
    finally:
        if driver:
            driver.quit()

def parse_count(text):
    """Parse numbers like 1.2K, 5.5M"""
    text = text.upper().replace(',', '')
    if 'K' in text:
        return int(float(text.replace('K', '')) * 1000)
    elif 'M' in text:
        return int(float(text.replace('M', '')) * 1000000)
    return int(text) if text.isdigit() else 0

@app.route('/')
def home():
    return jsonify({"message": "Instagram Analyzer API", "status": "ready"})

@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.get_json()
    username = data.get('username', '').strip()
    
    if not username:
        return jsonify({"error": "Username required"}), 400
    
    result = analyze_profile(username)
    return jsonify(result)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
