import sys
import jwt
from src.auth import SECRET_KEY

token = sys.argv[1]
print("segments:", token.count('.') + 1)
print("len:", len(token))
try:
    payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
    print('OK:', payload)
except Exception as e:
    print('ERREUR:', type(e).__name__, str(e))
