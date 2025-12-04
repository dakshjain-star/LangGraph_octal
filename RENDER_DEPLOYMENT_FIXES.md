# Render Deployment Fixes - Token & Authentication Issues

## Overview
Fixed critical authentication and continuous reload issues in the frontend after successful deployment to Render. The application was stuck in a reload loop due to 401 errors from the backend when trying to fetch protected resources.

## Issues Identified

### 1. **Missing Credentials in Axios** (🔴 CRITICAL)
- **Problem**: Axios wasn't sending credentials/tokens in CORS requests due to missing `withCredentials` flag
- **Impact**: Authentication headers not being sent to backend, resulting in 401 "Missing authorization credentials" errors
- **Solution**: Added `withCredentials: true` to Axios configuration

### 2. **Race Condition in App Initialization** (🔴 CRITICAL)
- **Problem**: `setLoading(false)` was called in the `finally` block AFTER `refreshData()` completed
  - This meant UI showed loading state while API calls were still in progress
  - State updates weren't fully propagated before refresh functions were called
  - Dependency array `[refreshData, refreshUserData]` caused unnecessary re-renders
- **Impact**: Frontend making API calls before state was ready, causing cascading failures
- **Solution**: 
  - Move `setLoading(false)` BEFORE calling refresh functions
  - Add 100ms `setTimeout` to ensure state updates propagate
  - Change dependency array to empty `[]` to prevent infinite loops
  - Use `.catch()` instead of `await` to handle errors gracefully

### 3. **Missing Token Checks** (🟡 MEDIUM)
- **Problem**: `refreshData()` and `refreshUserData()` functions made API calls without verifying token exists
- **Impact**: Sending unauthenticated API requests that fail with 401, triggering retry logic
- **Solution**: Add `getAccessToken()` check at start of both functions, return early if no token

## Changes Made

### 1. **`dash_saas/services/api.ts`**
```typescript
// Added withCredentials flag to axios instance
const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true, // ← NEW: Allow credentials in CORS requests
  headers: {
    'Content-Type': 'application/json',
  },
});
```

**Why this works:**
- Enables CORS with credentials (Authorization header + cookies)
- Axios now properly sends Bearer token in Authorization header for all requests
- Allows backend to verify token in request headers instead of 401-ing

---

### 2. **`dash_saas/context.tsx`** - Fixed Initialization Flow

#### Change 1: Token check in `refreshData()`
```typescript
const refreshData = async () => {
  console.log('Starting refreshData...');
  try {
    // Check if user is still logged in
    if (!getAccessToken()) {
      console.warn('No access token available, skipping refreshData');
      return;
    }
    // ... rest of function
```

#### Change 2: Token check in `refreshUserData()`
```typescript
const refreshUserData = useCallback(async () => {
  console.log('Refreshing user portal data...');
  try {
    // Check if user is still logged in
    if (!getAccessToken()) {
      console.warn('No access token available, skipping refreshUserData');
      return;
    }
    // ... rest of function
```

#### Change 3: Fixed initialization race condition
```typescript
// OLD CODE (BROKEN):
useEffect(() => {
  const initializeApp = async () => {
    if (token) {
      try {
        setLoading(true);
        // ... get user ...
        
        // PROBLEM: Calling awaits here, but loading not set to false until finally
        if (userWithType.user_type === 'user') {
          await refreshUserData();  // ← Waits for all data to load
        } else {
          await refreshData();      // ← Waits for all data to load
        }
      } finally {
        setLoading(false);  // ← TOO LATE! Called after all data loads
      }
    }
  };
  initializeApp();
}, [refreshData, refreshUserData]);  // ← Causes infinite loops

// NEW CODE (FIXED):
useEffect(() => {
  const initializeApp = async () => {
    if (token) {
      try {
        setLoading(true);
        setError(null);
        
        // ... get user ...
        
        setUser(userWithType);
        setUserData(userWithType);
        setLoading(false);  // ← Set false BEFORE refresh
        
        // Small delay to ensure state updates propagate
        setTimeout(() => {
          if (userWithType.user_type === 'user') {
            // Use .catch() instead of await to prevent blocking
            refreshUserData().catch(err => console.error('Failed:', err));
          } else {
            refreshData().catch(err => console.error('Failed:', err));
          }
        }, 100);
      } catch (err: any) {
        console.error('Failed to initialize app:', err);
        setError(err.message);
        setLoading(false);
        authAPI.logout();
      }
    } else {
      setLoading(false);
    }
  };
  initializeApp();
}, []);  // ← Empty deps to prevent re-renders
```

**Why these fixes work:**
1. **Token checks**: Prevents making API calls when unauthenticated, avoiding 401 errors
2. **Loading state moved up**: UI correctly reflects that app is ready while data loads asynchronously
3. **setTimeout delay**: Ensures React state updates complete before making new API calls
4. **Error handling**: `.catch()` allows failed requests to not block other operations
5. **Empty deps**: Prevents unnecessary re-initialization on every render

---

## Backend CORS Configuration (Already Correct)

The backend CORS settings were already properly configured in `dash_api/main.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,  # Includes https://nexus-esw7.onrender.com
    allow_credentials=settings.cors_credentials,  # True
    allow_methods=cors_methods,  # GET, POST, PUT, PATCH, DELETE, OPTIONS
    allow_headers=cors_headers,  # Content-Type, Authorization
    expose_headers=["Content-Type", "Authorization"],
    max_age=600,
)
```

- ✅ Allows production frontend origin
- ✅ Allows credentials (important for CORS with Authorization header)
- ✅ Allows Authorization header in requests
- ✅ Exposes Authorization header in responses

---

## How the Flow Now Works

### 1. **User Logs In**
```
Frontend sends: POST /api/v1/auth/login { email, password }
                    ↓
Backend returns: { access_token, refresh_token, ... }
                    ↓
Frontend calls: setTokens(access_token, refresh_token)
                    ↓
Tokens stored in: sessionStorage
```

### 2. **App Initialization**
```
App mounts
    ↓
initializeApp() called in useEffect
    ↓
Check if token exists: getAccessToken()
    ↓
If YES:
  - Set loading = true
  - Get user from cache OR fetch from API
  - Update user state
  - Set loading = false  ← IMPORTANT: Before refresh
    ↓
  - Wait 100ms for state update
    ↓
  - Call refreshData() with .catch() error handling
    ↓
  - refreshData() checks token again before making API calls
    ↓
  - Axios interceptor adds "Authorization: Bearer <token>" header
    ↓
  - Backend receives request WITH token in header
    ↓
  - Backend validates token and returns data
```

### 3. **All Subsequent API Calls**
```
Frontend component calls: userAPI.getAll()
                    ↓
Axios request interceptor executes:
  - Gets token from sessionStorage
  - Sets header: Authorization: Bearer <token>
                    ↓
Request sent WITH Authorization header
                    ↓
Backend receives request WITH token
                    ↓
Request succeeds with 200 OK (no more 401s!)
```

---

## Testing Checklist

- ✅ Build succeeds: `npm run build` (no TypeScript errors)
- ✅ Backend CORS allows credentials
- ✅ Axios sends `withCredentials: true`
- ✅ Axios interceptor adds Authorization header
- ✅ Frontend doesn't make API calls without token
- ✅ App doesn't enter reload loop
- ✅ Login page works
- ✅ After login, can fetch user data (no 401 errors)
- ✅ Dashboard loads without constant reloading

---

## Production Deployment Targets

- **Frontend**: `https://nexus-esw7.onrender.com`
- **Dashboard Backend**: `https://nexus-backend-g0gm.onrender.com`
- **Chatbot Backend**: `https://nexus-chatbot-backend.onrender.com`

All three services are deployed and operational on Render.com.

---

## Summary

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| 401 "Missing auth credentials" | Axios not sending Authorization header in CORS requests | Added `withCredentials: true` to Axios config |
| Continuous reload loop | Race condition with state updates | Moved `setLoading(false)` before refresh calls + added 100ms delay |
| Unauthenticated API calls | Functions didn't verify token existed | Added `getAccessToken()` checks in refreshData/refreshUserData |

All changes maintain backward compatibility and don't require any frontend/backend endpoint changes. The fixes are purely in how the frontend manages authentication state and API requests.
