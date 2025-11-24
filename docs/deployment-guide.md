# 🚀 Complete Deployment Pipeline

This guide walks you through deploying Sophia's backend to Render and frontend to Vercel with full observability.

---

## Part 1: Backend Deployment (Render)

The backend is deployed as a Docker-based web service on Render using `render.yaml` and `Dockerfile.backend`.

### Prerequisites
- Render account with the GitHub repository connected
- Python 3.10+ (already specified via `runtime.txt` in the repo)

### Configure Backend Service on Render

1. **Connect Repository to Render**
   - Push your changes to GitHub (including `render.yaml` and `Dockerfile.backend`)
   - In the Render dashboard, connect your GitHub repository
   - Render will automatically detect `render.yaml` and create the service

2. **Configure Service Settings**
   - **Environment**: `Docker`
   - **Dockerfile path**: `./Dockerfile.backend`
   - **Health check path**: `/health`
   - **Auto-Deploy**: Enable for automatic deployments on push to main branch

3. **Set Environment Variables as Secrets**

   In the service **Environment** tab, add the following variables (values should be set only in Render dashboard, **never** committed to repository):

   **AI Provider Keys:**
   - `MISTRAL_API_KEY` - Your Mistral AI API key
   - `INWORLD_API_KEY` - Your Inworld AI API key
   - `GOOGLE_API_KEY` - Your Google Gemini API key
   - `OPENAI_API_KEY` - Your OpenAI API key
   - `ANTHROPIC_API_KEY` - Your Anthropic API key

   **Supabase Configuration:**
   - `SUPABASE_URL` - Your Supabase project URL
   - `SUPABASE_ANON_KEY` - Your Supabase anon/public key
   - `SUPABASE_KEY` - Your Supabase service role key
   - `SUPABASE_DB_DSN` - PostgreSQL connection string (format: `postgresql+psycopg://postgres:password@host:port/database`)
   - `SUPABASE_BUCKET_AUDIO` - Audio storage bucket name (e.g., `audio-uploads`)
   - `SUPABASE_AUDIO_PREFIX` - Audio file prefix (e.g., `uploads/`)
   - `SUPABASE_DB_PASSWORD` - Database password

   **Application Configuration:**
   - `APP_NAME` - Application name (e.g., `Sophia Voice Backend - Production`)
   - `API_KEYS` - Comma-separated API keys for backend authentication
   - `API_RATE_LIMIT` - Rate limit (e.g., `30/minute`)
   - `REQUIRE_CONSENT` - Set to `true` for GDPR compliance

   **Observability (Optional):**
   - `OTEL_EXPORTER_OTLP_ENDPOINT` - Grafana Cloud OTLP endpoint
   - `OTEL_EXPORTER_OTLP_HEADERS` - Grafana authentication headers

   **Important Security Notes:**
   - Use Render's **Secret Files** feature for sensitive configuration
   - For local development, use `.env.example` as a template
   - **Never** commit real API keys or credentials to the repository
   - All production secrets should live only in Render dashboard

### Deploy Backend

1. **Manual Deploy:**
   - Click **Manual Deploy → Clear build cache & deploy** in the Render dashboard
   - Monitor build logs in real-time
   - Wait for deployment to complete (usually 5-10 minutes)

2. **Automatic Deploys:**
   - Once auto-deploy is enabled, pushing to main branch triggers deployment
   - Render will rebuild and redeploy automatically

### Verify Backend Deployment

✅ **Health Check:**
```bash
curl https://sophia-1st-mvp-xjml.onrender.com/health
✅ API Documentation:

Visit: https://sophia-1st-mvp-xjml.onrender.com/docs
Explore Swagger UI and test endpoints
✅ Test Key Endpoints:

/health - Should return {"status": "healthy"}
/transcribe - Test audio transcription
/chat - Test full conversation pipeline
/text-chat - Test text-only conversation
✅ Check Logs:

Review deployment logs in Render dashboard
Look for startup errors or missing environment variables
Verify all services initialized successfully
Part 2: Frontend Deployment (Vercel)
Prerequisites
Copy# Install Vercel CLI
npm i -g vercel

# Login to Vercel
vercel login
Deploy Frontend
Copy# Navigate to frontend directory
cd frontend-nextjs

# Install dependencies
npm install

# Deploy to production
vercel --prod
Configure Environment Variables in Vercel
Method 1: Via Vercel Dashboard (Recommended)

Go to your Vercel project → Settings → Environment Variables
Add the following variables for Production, Preview, and Development:
Authentication:

NEXTAUTH_URL - Your frontend URL (e.g., https://sophia.vercel.app)
NEXTAUTH_SECRET - Generate with: openssl rand -base64 32
DISCORD_CLIENT_ID - From Discord Developer Portal
DISCORD_CLIENT_SECRET - From Discord Developer Portal
Supabase:

NEXT_PUBLIC_SUPABASE_URL - Your Supabase project URL
NEXT_PUBLIC_SUPABASE_ANON_KEY - Your Supabase anon/public key
SUPABASE_SERVICE_ROLE_KEY - Your Supabase service role key (server-side only)
API Connection:

NEXT_PUBLIC_API_URL - Backend URL: https://sophia-1st-mvp-xjml.onrender.com
NEXT_PUBLIC_API_KEY - API key matching backend API_KEYS configuration
Method 2: Via Vercel CLI

Copyvercel env add NEXTAUTH_URL production
vercel env add NEXTAUTH_SECRET production
vercel env add DISCORD_CLIENT_ID production
vercel env add DISCORD_CLIENT_SECRET production
vercel env add NEXT_PUBLIC_SUPABASE_URL production
vercel env add NEXT_PUBLIC_SUPABASE_ANON_KEY production
vercel env add SUPABASE_SERVICE_ROLE_KEY production
vercel env add NEXT_PUBLIC_API_URL production
vercel env add NEXT_PUBLIC_API_KEY production
Note: Use frontend-nextjs/.env.example as a template for local development.

Verify Frontend Deployment
✅ Access Application:

Visit your Vercel deployment URL
Verify the landing page loads correctly
✅ Test Authentication:

Click "Login with Discord"
Complete OAuth flow
Verify redirect back to application
✅ Test Consent Modal:

New users should see GDPR consent modal
Verify modal blocks access until consent granted
Check Supabase user_consents table for hashed entry
✅ Test Voice Interface:

Grant microphone permissions
Record a test message
Verify transcription appears
Verify audio response plays back
✅ Test Chat Interface:

Send text messages
Verify responses display correctly
Check emotion indicators appear
✅ Check Logs:

Review Vercel deployment logs
Check browser console for errors
Verify API calls succeed
Part 3: Discord OAuth Setup
1. Create Discord Application
Visit: https://discord.com/developers/applications
Click New Application
Name your application (e.g., "Sophia AI Companion")
Go to OAuth2 → General
2. Configure OAuth2 Settings
Redirect URIs: Add the following redirect URIs:

Production: https://your-frontend.vercel.app/api/auth/callback/discord
Development: http://localhost:3000/api/auth/callback/discord
Scopes: Select the following OAuth2 scopes:

identify - Access to user's ID, username, avatar
email - Access to user's email address
3. Get Credentials
Copy Client ID from OAuth2 → General
Generate and copy Client Secret
Add both to Vercel environment variables:
DISCORD_CLIENT_ID
DISCORD_CLIENT_SECRET
4. Test OAuth Flow
Navigate to your frontend
Click "Login with Discord"
Authorize the application
Verify successful redirect and user data storage in Supabase
Part 4: Supabase Database Setup
Apply Database Schema
Option 1: Via Alembic (Recommended)

Copy# Ensure SUPABASE_DB_DSN is set in .env
export SUPABASE_DB_DSN="postgresql+psycopg://postgres:password@host:port/database"

# Apply migrations
alembic upgrade head
Option 2: Via Supabase SQL Editor

Execute the following SQL in Supabase SQL Editor:

Copy-- Users table
CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  discord_id TEXT UNIQUE NOT NULL,
  username TEXT,
  discriminator TEXT,
  avatar TEXT,
  email TEXT,
  has_consent BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- User consents table
CREATE TABLE IF NOT EXISTS user_consents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  discord_id TEXT NOT NULL,
  consent_hash TEXT NOT NULL,
  ip_address TEXT,
  timestamp TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  FOREIGN KEY (discord_id) REFERENCES users(discord_id)
);

-- Conversation sessions table
CREATE TABLE IF NOT EXISTS conversation_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  discord_id TEXT NOT NULL,
  session_data JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  FOREIGN KEY (discord_id) REFERENCES users(discord_id)
);

-- Emotion scores table
CREATE TABLE IF NOT EXISTS emotion_scores (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL,
  discord_id TEXT NOT NULL,
  emotion_type TEXT,
  confidence FLOAT,
  timestamp TIMESTAMPTZ DEFAULT NOW(),
  FOREIGN KEY (session_id) REFERENCES conversation_sessions(id),
  FOREIGN KEY (discord_id) REFERENCES users(discord_id)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_users_discord_id ON users(discord_id);
CREATE INDEX IF NOT EXISTS idx_consents_discord_id ON user_consents(discord_id);
CREATE INDEX IF NOT EXISTS idx_sessions_discord_id ON conversation_sessions(discord_id);
CREATE INDEX IF NOT EXISTS idx_emotions_session_id ON emotion_scores(session_id);
CREATE INDEX IF NOT EXISTS idx_emotions_discord_id ON emotion_scores(discord_id);
Enable Row-Level Security (RLS)
Critical Security Step: Before granting end-user access, execute the RLS policies:

Copy# In Supabase SQL Editor, execute enable_rls_policies.sql
# This ensures users can only access their own data
Copy-- Enable RLS on tables
ALTER TABLE conversation_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE emotion_scores ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only read their own sessions
CREATE POLICY users_read_own_sessions ON conversation_sessions
  FOR SELECT
  USING (discord_id = current_setting('app.current_user_discord_id'));

-- Policy: Users can only insert their own sessions
CREATE POLICY users_insert_own_sessions ON conversation_sessions
  FOR INSERT
  WITH CHECK (discord_id = current_setting('app.current_user_discord_id'));

-- Policy: Users can only read their own emotions
CREATE POLICY users_read_own_emotions ON emotion_scores
  FOR SELECT
  USING (discord_id = current_setting('app.current_user_discord_id'));

-- Policy: Users can only insert their own emotions
CREATE POLICY users_insert_own_emotions ON emotion_scores
  FOR INSERT
  WITH CHECK (discord_id = current_setting('app.current_user_discord_id'));
Configure Storage Bucket
Create Audio Uploads Bucket:

Go to Supabase → Storage
Create new bucket: audio-uploads
Set as Public or Private based on requirements
Set Bucket Policies:

Copy-- Allow authenticated users to upload audio
CREATE POLICY authenticated_users_upload ON storage.objects
  FOR INSERT
  TO authenticated
  WITH CHECK (bucket_id = 'audio-uploads');

-- Allow users to read their own audio files
CREATE POLICY users_read_own_audio ON storage.objects
  FOR SELECT
  TO authenticated
  USING (bucket_id = 'audio-uploads' AND (storage.foldername(name))[1] = auth.uid()::text);
Part 5: Grafana Cloud Setup
1. Create Grafana Cloud Account
Visit: https://grafana.com/products/cloud/
Sign up for Free Tier (includes OpenTelemetry support)
Note your Grafana Cloud instance URL
Create an API token with Editor permissions
2. Get OpenTelemetry Credentials
In Grafana Cloud, go to Connections → Add new connection
Select OpenTelemetry
Copy your OTLP endpoint (e.g., https://otlp-gateway-prod-us-central-0.grafana.net/otlp)
Generate authentication credentials:
Copyecho -n "instance_id:api_token" | base64
Add to Render environment variables:
OTEL_EXPORTER_OTLP_ENDPOINT = your OTLP endpoint
OTEL_EXPORTER_OTLP_HEADERS = Authorization=Basic <base64_credentials>
3. Import Dashboards
Via Grafana UI (Recommended):

Log into your Grafana Cloud instance
Navigate to Dashboards → Import
Upload JSON files from grafana-dashboards/ directory:
latency-overview.json
emotion-confidence.json
errors-fallbacks.json
Via Grafana API:

Copy# Set variables
GRAFANA_URL="https://your-instance.grafana.net"
GRAFANA_TOKEN="your_api_token"

# Import latency overview dashboard
curl -X POST \
  "${GRAFANA_URL}/api/dashboards/db" \
  -H "Authorization: Bearer ${GRAFANA_TOKEN}" \
  -H "Content-Type: application/json" \
  -d @grafana-dashboards/latency-overview.json

# Import emotion confidence dashboard
curl -X POST \
  "${GRAFANA_URL}/api/dashboards/db" \
  -H "Authorization: Bearer ${GRAFANA_TOKEN}" \
  -H "Content-Type: application/json" \
  -d @grafana-dashboards/emotion-confidence.json

# Import errors and fallbacks dashboard
curl -X POST \
  "${GRAFANA_URL}/api/dashboards/db" \
  -H "Authorization: Bearer ${GRAFANA_TOKEN}" \
  -H "Content-Type: application/json" \
  -d @grafana-dashboards/errors-fallbacks.json
4. Configure Data Sources
Add Prometheus Data Source:

Go to Connections → Data sources → Add data source
Select Prometheus
URL: Your Grafana Cloud Prometheus endpoint
Add authentication headers
Configure Retention:

Free tier: 14 days metrics retention
Configure scrape intervals (default: 15s)
Verify Data Flow:

Navigate to Explore
Query: sophia_* to see metrics
Verify spans appear in Tempo
5. Set Up Alerts (Optional)
Configure alerts for critical metrics:

High Error Rate Alert:

rate(sophia_errors_total[5m]) > 0.05
High Latency Alert:

histogram_quantile(0.95, rate(sophia_response_duration_seconds_bucket[5m])) > 5
Low Emotion Confidence Alert:

avg_over_time(sophia_emotion_confidence[1h]) < 0.5

Part 6: Testing Checklist
Backend Integration Tests
 Health Check: GET /health returns {"status": "healthy"}
 API Docs: /docs Swagger UI loads and displays all endpoints
 Transcription: /transcribe accepts audio files and returns text
 Full Pipeline: /chat processes voice input and returns audio response
 Text Chat: /text-chat handles text-only conversations
 LangGraph: /defi-chat integrates workflow orchestration
 Session Retrieval: /sessions/{id} returns conversation history
 CORS: Frontend can make cross-origin requests successfully
 Rate Limiting: API enforces rate limits correctly
 Authentication: API keys are validated on protected endpoints
Frontend Integration Tests
 Landing Page: Homepage loads without errors
 Discord OAuth: Login flow completes successfully
 User Profile: Discord username and avatar display correctly
 Consent Modal: Appears for new users and blocks access until accepted
 Consent Storage: Hashed consent record saved to Supabase
 Voice Recording: Microphone permissions granted and audio captured
 Audio Playback: Sophia's responses play back correctly
 Transcription Display: User's speech appears as text
 Text Messages: Typing and sending text works correctly
 Emotion Indicators: Emoji labels display with confidence scores
 Session Persistence: Conversation history persists across page refreshes
 Mobile Responsive: UI works on mobile devices
Observability Tests
 Grafana Dashboards: All 3 dashboards load with data
 OpenTelemetry Traces: Spans appear in Grafana Tempo
 Metrics Collection: Custom metrics (latency, emotions, errors) are recorded
 Real-time Updates: Dashboards update as conversations occur
 Alerting: Test alerts trigger correctly (if configured)

End-to-End Integration Tests
 Full Voice Conversation:
User speaks → audio captured
Transcription appears
Sophia responds with text
Audio plays back
Emotion indicators update
Session saved to database
 Emotion Accuracy: >90% confidence consistency across multiple turns
 Response Latency: <2.5s average roundtrip time (p95)
 GDPR Compliance: Consent blocking works; withdrawal removes access
 Error Handling: Graceful degradation when services fail
 Fallback Systems: Gemini fallback activates when Mistral fails
Part 7: Monitoring & Alerts
Key Performance Indicators (KPIs)
Metric	Target	Alert Threshold
Response Latency (p95)	<2.5s	>5s for 5 minutes
Error Rate	<1%	>5% for 5 minutes
Emotion Confidence (avg)	>0.7	<0.5 for 1 hour
API Availability	>99.9%	Health check fails
STT Latency	<500ms	>2s for 5 minutes
LLM Latency	<1.5s	>3s for 5 minutes
TTS Latency	<1s	>2s for 5 minutes

Recommended Alerts
Critical Alerts:

Service down (health check fails for 2 minutes)
Error rate >10% (immediate action required)
Database connection failures
Warning Alerts:

High latency (>5s p95 for 5 minutes)
Error rate >5% (investigate within 30 minutes)
Low emotion confidence (<0.5 for 1 hour)
High API rate limit rejections
Info Alerts:

Unusual traffic patterns
Fallback systems activated frequently
Memory usage >80%
Grafana Dashboard Guide
1. Latency Overview Dashboard:

Total roundtrip time breakdown
STT/LLM/TTS component latencies
P50, P95, P99 percentile tracking
Time series graphs by endpoint
2. Emotion Confidence Dashboard:

Average emotion confidence over time
Confidence distribution histogram
User vs Sophia emotion comparison
Emotion type frequency
3. Errors & Fallbacks Dashboard:

Error rate by endpoint
Error types and frequency
Fallback activation count
Service health status
Part 8: Environment Variables Reference
Backend Environment Variables (Render Secrets)
Required - AI Provider Keys:

CopyMISTRAL_API_KEY=your_mistral_api_key_here
INWORLD_API_KEY=your_inworld_api_key_here
GOOGLE_API_KEY=your_google_gemini_key_here
OPENAI_API_KEY=your_openai_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here
Required - Supabase Configuration:

CopySUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_supabase_anon_key_here
SUPABASE_KEY=your_supabase_service_role_key_here
SUPABASE_DB_DSN=postgresql+psycopg://postgres:password@host:port/database
SUPABASE_BUCKET_AUDIO=audio-uploads
SUPABASE_AUDIO_PREFIX=uploads/
SUPABASE_DB_PASSWORD=your_db_password_here
Required - Application Configuration:

CopyAPP_NAME=Sophia Voice Backend - Production
API_KEYS=your_backend_api_keys_comma_separated
API_RATE_LIMIT=30/minute
REQUIRE_CONSENT=true
Optional - Observability:

CopyOTEL_EXPORTER_OTLP_ENDPOINT=https://otlp-gateway-prod-us-central-0.grafana.net/otlp
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic <base64_credentials>
Frontend Environment Variables (Vercel)
Required - Authentication:

CopyNEXTAUTH_URL=https://your-frontend.vercel.app
NEXTAUTH_SECRET=<generate with: openssl rand -base64 32>
DISCORD_CLIENT_ID=your_discord_client_id
DISCORD_CLIENT_SECRET=your_discord_client_secret
Required - Supabase:

CopyNEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
Required - API Connection:

CopyNEXT_PUBLIC_API_URL=https://sophia-1st-mvp-xjml.onrender.com
NEXT_PUBLIC_API_KEY=your_backend_api_key
🎯 Success Criteria
Backend Deployment Success
✅ Service Live: https://sophia-1st-mvp-xjml.onrender.com/docs accessible
✅ Health Check: /health returns 200 OK
✅ All Endpoints Functional: Swagger UI shows all endpoints working
✅ Environment Variables Set: All required secrets configured in Render
✅ Logs Clean: No startup errors or missing configuration warnings
✅ Auto-Deploy Enabled: Pushes to main trigger automatic redeployment

Frontend Deployment Success
✅ Application Live: Vercel deployment URL accessible
✅ Discord OAuth: User login stores discord_id in Supabase users table
✅ GDPR Consent: Modal blocks usage until accepted; hashed entry in user_consents
✅ Voice Loop: Audio input → transcription → Sophia reply with audio + transcript
✅ Text Chat: Text messages send and receive responses correctly
✅ Emotion Visuals: Emoji labels display with confidence scores (≥90% consistency)
✅ Session Persistence: Conversation history persists across page refreshes
✅ Mobile Responsive: UI functions correctly on mobile devices

Observability Success
✅ Grafana Dashboards: All 3 dashboards imported and displaying live data
✅ OpenTelemetry Traces: Spans appearing in Grafana Tempo
✅ Metrics Flowing: Custom metrics (emotion, latency, errors) being collected
✅ Real-time Updates: Dashboards update as conversations occur
✅ Alerts Configured: Critical alerts set up and tested (optional)

Integration Success
✅ End-to-End Flow: User speaks → transcription → AI response → audio playback
✅ Database Operations: User data, sessions, emotions saved to Supabase
✅ RLS Policies: Users can only access their own data
✅ Performance Targets Met: <2.5s p95 latency, <1% error rate
✅ Security Verified: CORS, rate limiting, authentication all functional

🆘 Troubleshooting
Common Backend Issues
Issue: Render build fails

Check Dockerfile.backend exists and is valid
Verify render.yaml configuration is correct
Review build logs for missing dependencies
Ensure runtime.txt specifies correct Python version
Issue: Environment variables not loading

Verify all required variables set in Render dashboard
Check for typos in variable names
Ensure sensitive values are in "Secret" fields
Redeploy after adding new variables
Issue: Health check fails

Check /health endpoint implementation
Verify Render health check path is /health
Review application startup logs
Check database connection string is valid
Issue: Database connection fails

Verify SUPABASE_DB_DSN format is correct
Ensure using postgresql+psycopg:// prefix
Check Supabase database is running
Verify database password is correct
Run alembic upgrade head to apply migrations
Common Frontend Issues
Issue: Discord OAuth fails

Verify redirect URI matches exactly in Discord Developer Portal
Check DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET are correct
Ensure NEXTAUTH_URL matches your deployment URL
Generate new NEXTAUTH_SECRET if needed
Issue: API calls fail with CORS errors

Verify CORS_ALLOWED_ORIGINS includes frontend URL in backend
Check NEXT_PUBLIC_API_URL points to correct backend
Ensure NEXT_PUBLIC_API_KEY matches backend API_KEYS
Review browser console for specific CORS error messages
Issue: Voice recording doesn't work

Check browser microphone permissions granted
Verify WebRTC is supported in browser
Test on HTTPS (required for microphone access)
Check browser console for errors
Issue: Consent modal doesn't appear

Verify user_consents table exists in Supabase
Check REQUIRE_CONSENT=true in backend
Review Supabase connection in frontend
Check browser console for API errors
Common Grafana Issues
Issue: No data in dashboards

Verify OTEL_EXPORTER_OTLP_ENDPOINT is correct
Check OTEL_EXPORTER_OTLP_HEADERS authentication is valid
Ensure OpenTelemetry is initialized in backend
Generate some traffic to create metrics
Check Grafana data source configuration
Issue: Dashboards don't import

Verify JSON format is valid
Check Grafana API token has correct permissions
Ensure data sources are configured before importing
Try importing via UI instead of API
Performance Issues
Issue: High latency

Check Render service plan (free tier has cold starts)
Review component latencies in Grafana
Verify external API (Mistral, Inworld) response times
Check database query performance
Consider upgrading Render plan for better performance
Issue: Rate limit errors

Adjust API_RATE_LIMIT if needed
Implement exponential backoff in frontend
Check if legitimate traffic or potential abuse
Review rate limit logs in Render
📞 Support & Resources
Deployment Support
Check Logs First:

Render: Dashboard → Your Service → Logs
Vercel: Dashboard → Your Project → Deployments → Logs
Supabase: Dashboard → Logs & Activity
Review Documentation:

deployment-guide.md (this file)
SECURITY.md - Security best practices
observability.md - Monitoring setup
Test Components Individually:

Test backend /health endpoint
Test frontend authentication flow
Test database connections
Test API endpoints via Swagger UI
Verify Environment Variables:

Double-check all required variables are set
Ensure no typos in variable names
Verify values are correct (especially API keys)
Check variables are set in correct environment (production vs preview)