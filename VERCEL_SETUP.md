# Vercel Environment Variables Setup

## Issue Resolution: Frontend showing backend JSON instead of UI

The issue you experienced (Discord auth working but then showing raw JSON response) is caused by incorrect environment variables in Vercel.

## Required Vercel Environment Variables

Go to your Vercel dashboard → Project Settings → Environment Variables and set:

### Backend API Configuration
```
NEXT_PUBLIC_API_URL=https://sophia-1st-mvp-xjml.onrender.com
NEXT_PUBLIC_API_KEY=[your-production-api-key]
```

### Supabase Configuration
```
NEXT_PUBLIC_SUPABASE_URL=https://qitsfiaphigmkzfdyejp.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=[your-actual-supabase-anon-key]
SUPABASE_SERVICE_ROLE_KEY=[your-actual-service-role-key]
```

## Why This Fixes the Issue

1. **Before**: Frontend was calling `http://localhost:8000` (doesn't exist in production)
2. **After**: Frontend calls `https://sophia-1st-mvp-xjml.onrender.com` (your Render backend)

## Steps to Fix

1. **Go to Vercel Dashboard**
   - Open https://vercel.com/dashboard
   - Select your Sophia project

2. **Navigate to Settings**
   - Click "Settings" tab
   - Click "Environment Variables" in sidebar

3. **Add/Update Variables**
   - Add `NEXT_PUBLIC_API_URL` = `https://sophia-1st-mvp-xjml.onrender.com`
   - Add `NEXT_PUBLIC_API_KEY` = `[your-production-api-key]`
   - Update other Supabase variables if needed

4. **Redeploy**
   - Go to "Deployments" tab
   - Click "..." next to latest deployment
   - Click "Redeploy"

## Expected Result After Fix

✅ Discord auth works  
✅ Frontend UI loads properly (not JSON)  
✅ Voice calls connect to Render backend  
✅ All API calls route correctly  

## Architecture Overview

```
User → Vercel Frontend → Render Backend → AI Services
       (Next.js)         (FastAPI)       (Mistral/Inworld)
```

## Testing the Fix

After updating environment variables and redeploying:

1. Visit your Vercel URL
2. Complete Discord authentication
3. You should see the Sophia UI interface (not JSON)
4. Test voice calls and chat functionality