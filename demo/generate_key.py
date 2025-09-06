from cryptography.fernet import Fernet

# Generate a valid key
key = Fernet.generate_key().decode()
print('Your encryption key:')
print(key)
print('')
print('Add this to your .env file as:')
print(f'FIELD_ENCRYPTION_KEY="{key}"')
