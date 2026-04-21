# AWS Lambda Deployment Guide (Single File Version)

## ✅ What This Version Does

- ✅ **Single file**: `lambda_bot.py` - everything in one file
- ✅ **Webhook-based**: Uses API Gateway (not polling)
- ✅ **AWS Free Tier**: 1M requests/month free
- ✅ **All features**: Create, delete, list events
- ❌ **Limited**: No multi-file structure, simplified error handling


## 📋 Prerequisites

1. **AWS Account** (free tier available)
2. **Python 3.9+**
3. **GitHub repository** with your code

---

## 🚀 Step 1: Prepare Lambda Package

### Create requirements.txt for Lambda

```bash
cd ~/Documents/telegram-calendar-bot
cat > requirements-lambda.txt << 'EOF'
python-telegram-bot==21.9
openai>=1.30.0
google-auth>=2.29.0
google-auth-oauthlib>=1.2.0
google-auth-httplib2>=0.2.0
google-api-python-client>=2.130.0
requests>=2.31.0
EOF
```

### Create deployment package

```bash
# Create temp directory
mkdir lambda_package
cd lambda_package

# Install dependencies
pip install -r ../requirements-lambda.txt -t .

# Copy Lambda handler
cp ../lambda_bot.py .
cp ../lambda_function.py .

# Zip everything
zip -r lambda_function.zip .
```


## 🌐 Step 2: Deploy to AWS Lambda

### Via AWS Console

1. Go to **https://aws.amazon.com/console**
2. Search for **Lambda**
3. Click **Create function**
4. Configure:
   - **Function name**: `telegram-calendar-bot`
   - **Runtime**: Python 3.11
   - **Handler**: `lambda_function.lambda_handler`
   - **Timeout**: 30 seconds (default fine)
   - **Memory**: 512 MB (minimum recommended)

5. Upload the zip file:
   - Click **Upload from** → **Zip file**
   - Upload `lambda_function.zip`

6. Deploy!

### Or Via AWS CLI

```bash
# Configure AWS CLI first
aws configure

# Package
zip -r lambda_function.zip lambda_bot.py lambda_function.py

# Deploy
aws lambda create-function \
  --function-name telegram-calendar-bot \
  --runtime python3.11 \
  --role arn:aws:iam::YOUR_ACCOUNT_ID:role/lambda-role \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://lambda_function.zip \
  --timeout 30 \
  --memory-size 512
```


## 🔗 Step 3: Set Up API Gateway Webhook

### In AWS Console

1. Go to **API Gateway**
2. Click **Create API** → **REST API**
3. Configure:
   - **API name**: `telegram-webhook`
   - **Create**

4. Create method:
   - Resources → `/` → **Actions** → **Create Method** → **POST**
   - Integration type: **Lambda Function**
   - Select your `telegram-calendar-bot` function
   - **Save**

5. Enable CORS:
   - Actions → **Enable CORS and replace CORS headers**
   - **Yes, replace...**

6. Deploy:
   - Actions → **Deploy API**
   - **Stage**: `prod`
   - **Deploy**

7. **Copy the Invoke URL** (you'll need this!)

---

## 🔑 Step 4: Set Environment Variables

In Lambda console:

1. Click your function
2. Go to **Configuration** → **Environment variables**
3. Add:
   ```
   TELEGRAM_TOKEN=<your_telegram_token>
   ALLOWED_USER_ID=<your_user_id>
   GROQ_API_KEY=<your_grok_key>
   GOOGLE_CALENDAR_ID=primary
   GOOGLE_TOKEN_JSON=<base64_token>
   ```

4. **Save**

---

## 🤖 Step 5: Set Telegram Webhook

Once API Gateway is deployed, set Telegram webhook:

```bash
# Replace with your actual values
TELEGRAM_TOKEN="your_token"
API_GATEWAY_URL="https://xxxxx.execute-api.us-east-1.amazonaws.com/prod"

# Set webhook
curl -X POST "https://api.telegram.org/bot${TELEGRAM_TOKEN}/setWebhook" \
  -d "url=${API_GATEWAY_URL}"

# Verify
curl "https://api.telegram.org/bot${TELEGRAM_TOKEN}/getWebhookInfo"
```

---

## 📊 Verify It Works

1. **Check Lambda logs**:
   - Lambda console → **Monitor** → **Logs**
   - Click latest log group

2. **Test with Telegram**:
   - Send message to your bot
   - Check if it responds (should see logs)

3. **Test event creation**:
   ```
   /start
   ML exam May 5 at 10am
   /events
   ```

---

## 🎯 AWS Free Tier Limits

- ✅ **1M requests/month** (free)
- ✅ **400,000 GB-seconds/month** (free)
- ✅ **Each Lambda call**: ~100ms = very cheap
- ✅ **API Gateway**: 1M calls/month (free)

**Estimate**: Your bot uses ~1-2 GB-seconds per day
→ **Completely free** on free tier

---

## 📈 Monitoring

### CloudWatch Logs
```bash
# View recent logs
aws logs tail /aws/lambda/telegram-calendar-bot --follow
```

### Lambda Metrics
- Invocations
- Errors
- Duration
- Throttles

---

## ❌ Troubleshooting

### Bot not responding

1. **Check webhook is set**:
   ```bash
   curl "https://api.telegram.org/botTOKEN/getWebhookInfo"
   ```

2. **Check Lambda logs**:
   - Lambda console → Monitor → Logs

3. **Test Lambda directly**:
   ```bash
   aws lambda invoke --function-name telegram-calendar-bot response.json
   cat response.json
   ```

### Events not creating

1. Verify `GOOGLE_TOKEN_JSON` is set
2. Check logs for Google auth errors
3. Ensure token is still valid (refresh if needed)

### Timeout

1. Increase Lambda timeout: **Configuration** → **General** → **Timeout** → 60s
2. Optimize: Google API calls can be slow

---

## 🔄 Updating Code

1. Update `lambda_bot.py`
2. Repackage:
   ```bash
   cd lambda_package
   rm lambda_bot.py
   cp ../lambda_bot.py .
   cp ../lambda_function.py .
   cp ../lambda_function.py .
   zip -r ../lambda_function.zip .
   ```

3. Upload new version:
   ```bash
   aws lambda update-function-code \
     --function-name telegram-calendar-bot \
     --zip-file fileb://lambda_function.zip
   ```


## 💾 Cost Breakdown (Monthly)

| Service | Free Tier | Actual Cost |
|---------|-----------|------------|
| Lambda | 1M requests + 400K GB-s | $0 |
| API Gateway | 1M calls | $0 |
| Google Calendar | Unlimited | $0 |
| **Total** | | **$0/month** |

**Even after free tier:**
- Lambda: ~$0.17 per 1M requests
- API Gateway: ~$3.50 per 1M requests
- **Still very cheap** (~$5-10/month for heavy usage)

---

## ✅ Next Steps

1. Deploy to Lambda ✓
2. Set API Gateway webhook ✓
3. Add environment variables ✓
4. Set Telegram webhook ✓
5. Test in Telegram ✓

**Your bot is now live on AWS Lambda!** 🚀

---

## 📝 Important Notes

- **Single file**: Everything in `lambda_bot.py`
- **Stateless**: Each request is independent
- **Webhook**: Telegram sends events, Lambda responds
- **Cold starts**: First request might take 1-2s (acceptable)
- **Limited features**: Compared to polling version (this is simplified)

---

## 🆘 Quick Ref: Common Issues

| Issue | Solution |
|-------|----------|
| Timeout | Increase timeout in Lambda config |
| 502 Bad Gateway | Check Lambda logs, increase memory |
| Bot not responding | Verify webhook URL set correctly |
| Google auth fails | Check `GOOGLE_TOKEN_JSON` format |
| Cold start slow | Normal for first invoke, add memory to speed up |
