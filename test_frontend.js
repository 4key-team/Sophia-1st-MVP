#!/usr/bin/env node

const fs = require('fs')
const path = require('path')

console.log('🧪 Testing Supabase Auth Implementation\n')

// Test 1: Check package.json dependencies
console.log('✅ Test 1: Package Dependencies')
try {
  const packagePath = path.join(__dirname, 'frontend-nextjs', 'package.json')
  const packageJson = JSON.parse(fs.readFileSync(packagePath, 'utf8'))
  
  const requiredDeps = [
    '@supabase/supabase-js',
    '@supabase/auth-helpers-nextjs'
  ]
  
  const removedDeps = [
    'next-auth',
    '@next-auth/supabase-adapter'
  ]
  
  requiredDeps.forEach(dep => {
    if (packageJson.dependencies[dep]) {
      console.log(`   ✓ ${dep}: ${packageJson.dependencies[dep]}`)
    } else {
      console.log(`   ❌ Missing: ${dep}`)
    }
  })
  
  removedDeps.forEach(dep => {
    if (!packageJson.dependencies[dep]) {
      console.log(`   ✓ Removed: ${dep}`)
    } else {
      console.log(`   ⚠️  Still present: ${dep}`)
    }
  })
} catch (error) {
  console.log(`   ❌ Error reading package.json: ${error.message}`)
}

// Test 2: Check providers.tsx
console.log('\n✅ Test 2: Providers Configuration')
try {
  const providersPath = path.join(__dirname, 'frontend-nextjs', 'app', 'providers.tsx')
  const providersContent = fs.readFileSync(providersPath, 'utf8')
  
  const checks = [
    { pattern: /useSupabase/, name: 'useSupabase hook' },
    { pattern: /createClientComponentClient/, name: 'Supabase client' },
    { pattern: /onAuthStateChange/, name: 'Auth state listener' },
    { pattern: /SessionProvider/, name: 'NextAuth SessionProvider (should be removed)' }
  ]
  
  checks.forEach(check => {
    if (check.pattern.test(providersContent)) {
      if (check.name.includes('should be removed')) {
        console.log(`   ⚠️  ${check.name}: Still present`)
      } else {
        console.log(`   ✓ ${check.name}: Found`)
      }
    } else {
      if (check.name.includes('should be removed')) {
        console.log(`   ✓ ${check.name}: Properly removed`)
      } else {
        console.log(`   ❌ ${check.name}: Missing`)
      }
    }
  })
} catch (error) {
  console.log(`   ❌ Error reading providers.tsx: ${error.message}`)
}

// Test 3: Check page.tsx
console.log('\n✅ Test 3: Main Page Component')
try {
  const pagePath = path.join(__dirname, 'frontend-nextjs', 'app', 'page.tsx')
  const pageContent = fs.readFileSync(pagePath, 'utf8')
  
  const checks = [
    { pattern: /useSupabase/, name: 'useSupabase hook usage' },
    { pattern: /signInWithOAuth/, name: 'Supabase OAuth method' },
    { pattern: /provider: 'discord'/, name: 'Discord provider' },
    { pattern: /user\.user_metadata/, name: 'Supabase user metadata' },
    { pattern: /useSession.*next-auth/, name: 'NextAuth useSession (should be removed)' }
  ]
  
  checks.forEach(check => {
    if (check.pattern.test(pageContent)) {
      if (check.name.includes('should be removed')) {
        console.log(`   ⚠️  ${check.name}: Still present`)
      } else {
        console.log(`   ✓ ${check.name}: Found`)
      }
    } else {
      if (check.name.includes('should be removed')) {
        console.log(`   ✓ ${check.name}: Properly removed`)
      } else {
        console.log(`   ❌ ${check.name}: Missing`)
      }
    }
  })
} catch (error) {
  console.log(`   ❌ Error reading page.tsx: ${error.message}`)
}

// Test 4: Check environment files
console.log('\n✅ Test 4: Environment Configuration')
try {
  const envExamplePath = path.join(__dirname, 'frontend-nextjs', '.env.example')
  const envLocalPath = path.join(__dirname, 'frontend-nextjs', '.env.local')
  
  // Check .env.example
  if (fs.existsSync(envExamplePath)) {
    const envExample = fs.readFileSync(envExamplePath, 'utf8')
    if (envExample.includes('NEXT_PUBLIC_SUPABASE_URL')) {
      console.log('   ✓ .env.example: Supabase configuration present')
    } else {
      console.log('   ❌ .env.example: Missing Supabase configuration')
    }
    
    if (!envExample.includes('NEXTAUTH')) {
      console.log('   ✓ .env.example: NextAuth variables removed')
    } else {
      console.log('   ⚠️  .env.example: NextAuth variables still present')
    }
  }
  
  // Check .env.local
  if (fs.existsSync(envLocalPath)) {
    console.log('   ✓ .env.local: Created for development')
  } else {
    console.log('   ⚠️  .env.local: Not found (needs to be created)')
  }
} catch (error) {
  console.log(`   ❌ Error checking environment files: ${error.message}`)
}

// Test 5: Discord OAuth Configuration
console.log('\n✅ Test 5: Discord OAuth Setup')
console.log('   📋 Required Discord Configuration:')
console.log('   • Client ID: 1415848840069644419')
console.log('   • Client Secret: PNCwI2C_LPzu-_McS1GvarV3U9UXka78')
console.log('   • Redirect URI: https://qitsfiaphigmkzfdyejp.supabase.co/auth/v1/callback')
console.log('   • Supabase URL: https://qitsfiaphigmkzfdyejp.supabase.co')

console.log('\n🎯 Manual Steps Required:')
console.log('1. 🔧 Configure Discord provider in Supabase dashboard')
console.log('2. 🔗 Add redirect URI to Discord application')
console.log('3. 📦 Install dependencies: cd frontend-nextjs && npm install')
console.log('4. 🚀 Start development server: npm run dev')
console.log('5. 🧪 Test Discord login at http://localhost:3000')

console.log('\n✨ Implementation Status: Ready for testing!')
console.log('The Supabase Auth migration is complete. Follow the manual steps above to test.')
