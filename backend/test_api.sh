#!/usr/bin/env bash
API="http://localhost:8000"
USERNAME="wbekkal"
PASSWORD="12341234Wb!?"
MY_USER_ID=1
OTHER_USER_ID=2
TEST_MOVIE_ID=1

G="\033[32m✅" R="\033[31m❌" NC="\033[0m"
pass=0; fail=0

expect() {
  local label=$1 expected=$2
  local status=$(echo "$3" | grep -oE 'HTTP/[0-9.]+ [0-9]+' | tail -1 | awk '{print $2}')
  if [ "$status" = "$expected" ]; then echo -e "$G $label$NC"; ((pass++))
  else echo -e "$R $label → got $status, expected $expected$NC"; ((fail++)); fi
}

# ── TOKEN ──
echo -e "\n── 1) OAUTH2 TOKEN ──"
TOKEN=$(curl -s -X POST "$API/oauth/token/" -H "Content-Type: application/json" \
  -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('access',''))")
[ -z "$TOKEN" ] && echo -e "$R Token failed — aborting$NC" && exit 1
echo -e "$G Token obtained$NC"; ((pass++))
A="Authorization: Bearer $TOKEN"
expect "Wrong credentials → 401" 401 "$(curl -si -X POST "$API/oauth/token/" \
  -H "Content-Type: application/json" -d '{"username":"fake","password":"wrong"}')"

# ── USERS (route API officielle: /api/users/) ──
echo -e "\n── 2) USERS ──"
expect "GET /api/users no auth → 401"     401 "$(curl -si "$API/api/users/")"
expect "GET /api/users auth → 200"        200 "$(curl -si "$API/api/users/" -H "$A")"
expect "GET /api/users/$MY_USER_ID own → 200"        200 "$(curl -si "$API/api/users/$MY_USER_ID/" -H "$A")"
expect "GET /api/users/$OTHER_USER_ID other → 200"   200 "$(curl -si "$API/api/users/$OTHER_USER_ID/" -H "$A")"
expect "GET /api/users/999 → 404"         404 "$(curl -si "$API/api/users/999/" -H "$A")"
expect "PATCH /api/users/$MY_USER_ID own → 200"      200 "$(curl -si -X PATCH "$API/api/users/$MY_USER_ID/" \
  -H "$A" -H "Content-Type: application/json" -d '{"username":"wbekkal"}')"
expect "PATCH /api/users/$OTHER_USER_ID other → 403" 403 "$(curl -si -X PATCH "$API/api/users/$OTHER_USER_ID/" \
  -H "$A" -H "Content-Type: application/json" -d '{"username":"hacker"}')"

# Email privacy
curl -s "$API/api/users/$OTHER_USER_ID/" -H "$A" | grep -q '"email"' \
  && { echo -e "$R Email exposed on other profile$NC"; ((fail++)); } \
  || { echo -e "$G Email hidden on other profile$NC"; ((pass++)); }
curl -s "$API/api/users/$MY_USER_ID/" -H "$A" | grep -q '"email"' \
  && { echo -e "$G Email present on own profile$NC"; ((pass++)); } \
  || { echo -e "$R Email missing on own profile$NC"; ((fail++)); }

# ── MOVIES ──
echo -e "\n── 3) MOVIES ──"
expect "GET /api/movies no auth → 200"   200 "$(curl -si "$API/api/movies/")"
expect "GET /api/movies auth → 200"      200 "$(curl -si "$API/api/movies/" -H "$A")"
expect "GET /api/movies/$TEST_MOVIE_ID → 200" 200 "$(curl -si "$API/api/movies/$TEST_MOVIE_ID/" -H "$A")"

# ── COMMENTS ──
echo -e "\n── 4) COMMENTS ──"
expect "GET /api/comments no auth → 401"  401 "$(curl -si "$API/api/comments/")"
expect "GET /api/comments auth → 200"     200 "$(curl -si "$API/api/comments/" -H "$A")"

CID=$(curl -s -X POST "$API/api/comments/" -H "$A" -H "Content-Type: application/json" \
  -d "{\"movie_id\":$TEST_MOVIE_ID,\"content\":\"test\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
expect "POST /api/comments → 201"        201 "$(curl -si -X POST "$API/api/comments/" \
  -H "$A" -H "Content-Type: application/json" -d "{\"movie_id\":$TEST_MOVIE_ID,\"content\":\"x\"}")"
expect "POST /api/movies/:id/comments → 201" 201 "$(curl -si -X POST "$API/api/movies/$TEST_MOVIE_ID/comments/" \
  -H "$A" -H "Content-Type: application/json" -d '{"content":"via movie route"}')"
expect "GET /api/comments/$CID → 200"    200 "$(curl -si "$API/api/comments/$CID/" -H "$A")"
expect "PATCH /api/comments/$CID → 200"  200 "$(curl -si -X PATCH "$API/api/comments/$CID/" \
  -H "$A" -H "Content-Type: application/json" -d '{"content":"edited"}')"
expect "DELETE /api/comments/$CID → 204" 204 "$(curl -si -X DELETE "$API/api/comments/$CID/" -H "$A")"

# ── UNKNOWN /api/ → 404 ──
echo -e "\n── 5) UNKNOWN ROUTES → 404 ──"
expect "GET /api/does-not-exist → 404"        404 "$(curl -si "$API/api/does-not-exist/" -H "$A")"
expect "GET /api/movies/search → 404"         404 "$(curl -si "$API/api/movies/search/" -H "$A")"
expect "GET /api/register → 404"              404 "$(curl -si "$API/api/register/" -H "$A")"

# ── INTERNAL ROUTES (frontend only) ──
echo -e "\n── 6) INTERNAL ROUTES ──"
expect "GET /internal/movies/search no auth → 401" 401 "$(curl -si "$API/internal/movies/search/?q=test")"

# ── FORM VALIDATION ──
echo -e "\n── 7) FORM VALIDATION ──"
expect "Register short password → 400"  400 "$(curl -si -X POST "$API/internal/auth/register/" \
  -H "Content-Type: application/json" \
  -d '{"username":"t","email":"t@t.com","first_name":"T","last_name":"T","password":"short"}')"
expect "Register invalid email → 400"   400 "$(curl -si -X POST "$API/internal/auth/register/" \
  -H "Content-Type: application/json" \
  -d '{"username":"t","email":"notemail","first_name":"T","last_name":"T","password":"Valid1234!"}')"
expect "Register missing fields → 400"  400 "$(curl -si -X POST "$API/internal/auth/register/" \
  -H "Content-Type: application/json" -d '{"username":"t"}')"

echo -e "\n══════════════════════════════════"
echo -e "$G Passed: $pass$NC  $R Failed: $fail$NC"
echo "══════════════════════════════════"