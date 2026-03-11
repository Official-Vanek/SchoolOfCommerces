# SMS OTP Setup Guide - School Of Commerce

## 🔧 Twilio SMS Integration

### Current Status:
- ✅ Twilio library installed
- ✅ Backend code integrated
- ⚠️ **Needs Twilio credentials to work**

Without Twilio credentials, OTP is sent via **email fallback (Demo Mode)**

---

## 📱 How to Enable Real SMS OTP

### Step 1: Create Twilio Account

1. Go to https://www.twilio.com/
2. Sign up for free account
3. Verify your email and phone
4. You'll get **$15 free credit** for testing

### Step 2: Get Credentials

In your Twilio Console Dashboard:

1. **Account SID**: Found on main dashboard
   - Example: `ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

2. **Auth Token**: Click "Show" to reveal
   - Example: `your_secret_auth_token_here`

3. **Phone Number**: 
   - Go to "Phone Numbers" → "Manage" → "Buy a number"
   - Choose a number with SMS capability
   - Example: `+1234567890`
   - **Free tier**: Get one free phone number

### Step 3: Update Backend Configuration

Edit `/app/backend/.env`:

```bash
# Twilio SMS Configuration
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_secret_auth_token_here
TWILIO_PHONE_NUMBER=+1234567890
```

**Important:**
- Use your actual Twilio credentials
- Phone number must include country code (+91 for India, +1 for US)
- Keep Auth Token secret

### Step 4: Restart Backend

```bash
sudo supervisorctl restart backend
```

### Step 5: Test

1. Login as student
2. Go to `/verify-account`
3. Enter phone number with country code: `+919876543210`
4. Click "Send OTP"
5. You should receive SMS on your phone!

---

## 🧪 Testing Without Twilio (Current Setup)

**Demo Mode Activated:**
- OTP sent to user's registered email
- Email contains large OTP display
- Message explains Twilio not configured
- Perfect for development/testing

**To Test Demo Mode:**
1. Just send OTP normally
2. Check email inbox for OTP
3. Enter OTP on verification page

---

## 💰 Twilio Pricing

### Free Tier:
- $15 free credit on signup
- ~500 SMS messages
- 1 free phone number
- Perfect for testing and small projects

### Paid (after free credit):
- SMS: ~$0.0075 - $0.02 per message (varies by country)
- Phone number: ~$1/month
- India SMS: ~₹0.60 per message
- Very affordable for production

---

## 🔐 Security Best Practices

1. **Never commit** Twilio credentials to Git
2. **Use environment variables** only
3. **Rotate Auth Token** periodically
4. **Monitor usage** in Twilio dashboard
5. **Set spending limits** in Twilio account

---

## 📞 Phone Number Format

**Always include country code:**

✅ Correct:
- India: `+919876543210`
- US: `+11234567890`
- UK: `+441234567890`

❌ Wrong:
- `9876543210` (missing country code)
- `919876543210` (missing +)

---

## 🐛 Troubleshooting

### "Twilio not configured" message
**Solution**: Add Twilio credentials to `.env`

### SMS not received
**Check:**
1. Phone number includes country code
2. Twilio phone number is SMS-enabled
3. You have Twilio credit balance
4. Check Twilio logs dashboard

### "Invalid phone number" error
**Solution**: Use E.164 format with country code (+)

### SMS delayed
**Normal**: Can take 5-30 seconds
**Check**: Twilio delivery logs

---

## 🌍 International SMS

Twilio supports SMS to **190+ countries**

Some countries require additional verification:
- India: Register your sender ID
- China: Special approval needed
- Check Twilio docs for specific countries

---

## 📊 Monitoring

View SMS logs in Twilio Dashboard:
- https://console.twilio.com/
- Go to "Monitor" → "Logs" → "Messages"
- See delivery status, errors, timestamps

---

## 🔄 Fallback System

Current implementation has automatic fallback:

1. **Try Twilio SMS** (if configured)
   ↓ (if fails)
2. **Fallback to Email** (always works)
   ↓
3. **Log OTP** to backend logs (for debugging)

This ensures OTP always reaches user somehow!

---

## 📝 Summary

**Current Setup:**
- ✅ Code ready for SMS
- ✅ Twilio integrated
- ✅ Email fallback working
- ⏳ Needs Twilio credentials

**To Enable SMS:**
1. Get Twilio account (5 minutes)
2. Add 3 environment variables
3. Restart backend
4. Done! ✨

**Cost:** Free for testing, ~₹0.60/SMS in production
