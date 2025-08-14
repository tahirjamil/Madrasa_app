import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from werkzeug.security import generate_password_hash, check_password_hash
from config.config import Config

dummy_password = Config.DUMMY_PASSWORD

hash = generate_password_hash(dummy_password)

print(dummy_password)

print(hash)

print(check_password_hash(hash, dummy_password))

print(check_password_hash(hash, "Dummy@123"))