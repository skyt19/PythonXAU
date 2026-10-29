# MT5 Credentials Setup Guide

## Current Status
✗ MT5 credentials are **NOT configured**  
✓ `.env` file created and ready  
✓ `.env` is properly ignored by git (credentials won't be committed)

## What You Need

To connect PythonXAU to your HFM Demo MT5 account, you need:

1. **MT5 Account Login** (numeric ID)
2. **MT5 Account Password**
3. **MT5 Server Name** (exact name from MT5 terminal)

## How to Find Your Credentials

### In MetaTrader 5 Desktop Application:

1. **Open MT5 Terminal**
2. **Go to Tools → Options → Account** (or press Ctrl+O)
3. You will see:
   - **Login:** 12-digit number (e.g., `235156747`)
   - **Server:** Exact server name (e.g., `HFMarketsGlobal-Demo 4` or `HFM-Demo`)
   - **Password:** You should know this from account registration

### In HFM Client Portal:

1. Log in to your HFM account
2. Go to **My Accounts** → **MT5 Demo Accounts**
3. Find your demo account details:
   - Account Number (Login)
   - Server Name
   - Password (if you forgot it, you can reset it)

## How to Configure

### Option 1: Edit .env file directly

1. Open `C:\z\.env` in any text editor
2. Fill in your credentials:

```env
MT5_LOGIN=YOUR_ACCOUNT_NUMBER
MT5_PASSWORD=YOUR_PASSWORD
MT5_SERVER=HFMarketsGlobal-Demo 4
```

**Example:**
```env
MT5_LOGIN=235156747
MT5_PASSWORD=MySecurePassword123!
MT5_SERVER=HFMarketsGlobal-Demo 4
```

3. Save the file

### Option 2: Use environment variables (advanced)

If you prefer not to store credentials in a file, you can set them as environment variables:

**PowerShell:**
```powershell
$env:MT5_LOGIN="YOUR_ACCOUNT_NUMBER"
$env:MT5_PASSWORD="YOUR_PASSWORD"
$env:MT5_SERVER="HFMarketsGlobal-Demo 4"
```

**Command Prompt:**
```cmd
set MT5_LOGIN=YOUR_ACCOUNT_NUMBER
set MT5_PASSWORD=YOUR_PASSWORD
set MT5_SERVER=HFMarketsGlobal-Demo 4
```

## Verify Configuration

After filling in your credentials, verify the configuration:

```bash
python -c "from app.config import config; print(f'Login: {\"SET\" if config.mt5_login else \"EMPTY\"}'); print(f'Password: {\"SET\" if config.mt5_password else \"EMPTY\"}'); print(f'Server: {config.mt5_server}')"
```

Expected output when configured:
```
Login: SET
Password: SET
Server: HFMarketsGlobal-Demo 4
```

## Test MT5 Connection

Once configured, test the connection:

```bash
python scripts/collect_data.py --check
```

Expected output:
```
✓ MT5 connected: HF Markets Ltd., build XXXX
✓ MT5 is available for data collection
```

## Common Server Names for HFM Demo

- `HFMarketsGlobal-Demo 4`
- `HFMarketsGlobal-Demo`
- `HFM-Demo`
- `HFMarkets-Demo`

**Important:** Use the **exact** server name from your MT5 terminal. Even small differences (spaces, numbers) will cause connection failures.

## Security Notes

✓ `.env` is automatically ignored by git  
✓ Passwords are masked in logs  
✓ Configuration is validated on load  
✓ Only demo accounts are supported (enforced in code)  

**NEVER commit `.env` to version control!**

## Troubleshooting

### "MT5 initialization failed"
- Make sure MT5 is installed: Check `C:\Program Files\MetaTrader 5\terminal64.exe`
- Try reinstalling MT5 from HFM website

### "MT5 login failed"
- Verify login number is correct (no letters, just digits)
- Check password (case-sensitive)
- Confirm exact server name from MT5 terminal
- Ensure it's a **demo** account (live accounts are blocked)

### "Configuration is INCOMPLETE"
- Make sure there are no spaces around the `=` sign
- Values should not have quotes in the .env file
- Check file is saved as `.env` (not `.env.txt`)

## Next Steps

After configuring credentials:

1. **Verify configuration** (see above)
2. **Test MT5 connection** with `python scripts/collect_data.py --check`
3. **Collect historical data** with `python scripts/collect_data.py --days 365`
4. **Train models** with `python scripts/train_models.py`
5. **Start the application** with `python app/main.py`

---

For more information, see:
- `README.md` - Project overview
- `.env.example` - All available configuration options
- `app/config.py` - Configuration validation rules
