# gdrive_auth.py ko replace karo:
from google_auth_oauthlib.flow import InstalledAppFlow
import pickle

SCOPES = ['https://www.googleapis.com/auth/drive']

flow = InstalledAppFlow.from_client_secrets_file(
    'credentials.json', SCOPES)

# Manual authorization - no local server needed
flow.redirect_uri = 'urn:ietf:wg:oauth:2.0:oob'
auth_url, _ = flow.authorization_url(prompt='consent')

print('Please go to this URL and authorize:')
print(auth_url)
print('\nEnter the authorization code: ')
code = input().strip()

flow.fetch_token(code=code)
creds = flow.credentials

with open('token.pickle', 'wb') as token:
    pickle.dump(creds, token)

print("✅ Authentication successful! token.pickle created.")