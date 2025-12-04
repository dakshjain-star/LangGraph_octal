# Render Deployment Verification Checklist

## Pre-Deployment Checks ✅

- [x] Frontend builds without errors: `npm run build` 
- [x] Axios configured with `withCredentials: true`
- [x] Token checks added to `refreshData()` and `refreshUserData()`
- [x] App initialization race condition fixed
- [x] CORS middleware includes production frontend URL
- [x] Backend credentials flag is `True`
- [x] Authorization header added to CORS allowed headers

## Deployment Steps

### 1. Frontend Deployment (`https://nexus-esw7.onrender.com`)
```bash
cd dash_saas
npm run build
# Deploy dist/ folder to Render static site
```

### 2. Backend Deployment (`https://nexus-backend-g0gm.onrender.com`)
```bash
cd dash_api
# Already deployed - verify running with:
# https://nexus-backend-g0gm.onrender.com/health
```

### 3. Chatbot Deployment (`https://nexus-chatbot-backend.onrender.com`)
```bash
# Already deployed
```

---

## Post-Deployment Testing Checklist

### Critical Tests (Must Pass)

- [ ] **Login Works**
  - Navigate to `https://nexus-esw7.onrender.com`
  - Enter email/password
  - Should NOT see continuous reloading
  - Should redirect to dashboard

- [ ] **No 401 Errors**
  - Open DevTools → Network tab
  - Should NOT see red 401 errors after login
  - All API requests should return 200/201

- [ ] **Dashboard Loads**
  - Should see users list
  - Should see projects list
  - Should see tasks list
  - No error messages in console

- [ ] **WebSocket Connects**
  - Open DevTools → Network tab
  - Filter by "ws"
  - Should see WebSocket connection to Render backend
  - Connection should be "101 Switching Protocols"

- [ ] **Token Persistence**
  - Open DevTools → Application → Session Storage
  - Should see `access_token` and `refresh_token`
  - After page reload, should NOT return to login page

### Additional Tests (Nice to Have)

- [ ] **Create Task**
  - Create new task
  - Should appear in task list immediately (WebSocket)
  - No 401 errors in console

- [ ] **Update Profile**
  - Go to Profile page
  - Upload avatar or change info
  - Should work without errors

- [ ] **Logout**
  - Click logout button
  - Should redirect to login
  - Session storage should be cleared
  - Token in session storage should be gone

- [ ] **User Portal**
  - Click "Individual User? Login here"
  - Login as a regular user (non-admin)
  - Should access user portal at `/user` routes

---

## Troubleshooting

### Symptom: Continuous Reload Loop
**Diagnosis:**
- Check if token is in sessionStorage (DevTools → Application)
- Check if Authorization header is being sent (DevTools → Network → Request Headers)

**Solution:**
- Clear sessionStorage and try login again
- Check that `withCredentials: true` is in Axios config
- Verify backend CORS includes frontend URL

### Symptom: 401 Errors After Login
**Diagnosis:**
- Token exists but not being sent in headers
- CORS issue preventing credentials from being sent

**Solution:**
- Verify `withCredentials: true` in Axios
- Verify `allow_credentials=True` in backend CORS middleware
- Check that Authorization is in `allow_headers`

### Symptom: WebSocket Connection Failed
**Diagnosis:**
- Check if WSS (Secure WebSocket) is connecting to correct URL
- Network might be blocking WebSocket

**Solution:**
- Check browser console for WebSocket errors
- Verify `WS_BASE_URL` is correct (should be `wss://nexus-backend-g0gm.onrender.com`)

### Symptom: CORS Error in Browser Console
**Diagnosis:**
- Frontend URL not in backend CORS origins list
- Missing `allow_credentials` flag

**Solution:**
- Add frontend URL to `CORS_ORIGINS` environment variable in backend
- Set `CORS_CREDENTIALS=True` in backend `.env`

---

## Environment Variables to Verify

### Backend (`dash_api/.env`)
```
# Should contain:
CORS_ORIGINS=https://nexus-esw7.onrender.com,http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173
CORS_CREDENTIALS=True
MONGODB_URL=mongodb+srv://[YOUR_CREDENTIALS]
JWT_SECRET_KEY=[SET_IN_PRODUCTION]
```

### Frontend (`dash_saas/api.config.ts`)
```typescript
// Should be:
export const API_BASE_URL = 'https://nexus-backend-g0gm.onrender.com';
```

---

## Logs to Check

### Frontend Console (`DevTools → Console`)
```
✅ GOOD:
- "Current user data: {...}"
- "Starting refreshData..."
- "Setting users: X"
- "Setting tasks: X"

❌ BAD:
- "Failed to refresh data: 401"
- "Failed to initialize app: 401"
- "Missing authorization credentials"
```

### Backend Logs (`Render Dashboard`)
```
✅ GOOD:
- "Starting up Dash SaaS API..."
- "API running at..."
- "GET /api/v1/users/ HTTP/1.1" 200
- "POST /api/v1/auth/login HTTP/1.1" 200

❌ BAD:
- "GET /api/v1/users/ HTTP/1.1" 401
- "Missing authorization credentials"
- "CORS error"
```

---

## Success Indicators

If everything is working correctly, you should see:

1. ✅ Login page loads
2. ✅ Can login with admin credentials
3. ✅ Dashboard loads with user/task/project data
4. ✅ NO continuous reloading
5. ✅ NO 401 errors in network tab
6. ✅ Token stored in sessionStorage
7. ✅ WebSocket connected (green indicator)
8. ✅ Real-time updates work (create task appears immediately)
9. ✅ No errors in browser console
10. ✅ Can navigate between pages

---

## Rollback Instructions

If something breaks, revert to previous version:
```bash
git revert 3f57405  # Revert latest commit
git push origin main
# Redeploy on Render
```

Or manually revert the two files:
1. `dash_saas/context.tsx` - Remove token checks and fix initialization
2. `dash_saas/services/api.ts` - Remove `withCredentials: true`

---

## Contact & Support

If deployment still has issues:
1. Check Render deployment logs
2. Verify MongoDB connection string
3. Ensure all three services are running
4. Clear browser cache and try again
5. Check that SMTP credentials are valid (for password reset)

