#!/usr/bin/env bash
set -e

API="http://localhost:8000"
USERNAME="wbekkal"
PASSWORD="12341234Wb!?"
MY_USER_ID=1
OTHER_USER_ID=2
TEST_MOVIE_ID=1

function print_title() {
  echo
  echo "============= $1 ============="
}

function expect() {
  local label=$1
  local expected=$2
  local actual=$3
  if echo "$actual" | grep -qE "HTTP/[0-9.]+ $expected"; then
    echo "✅ $label → $expected"
  else
    STATUS=$(echo "$actual" | grep -oE 'HTTP/[0-9.]+ [0-9]+' | head -1 | awk '{print $2}')
    echo "❌ $label → attendu $expected, obtenu $STATUS"
  fi
}

# ========= 1) TOKEN =========
print_title "1) Obtenir un token via /oauth/token/"
RESPONSE=$(curl -s -X POST "$API/oauth/token/" \
  -H "Content-Type: application/json" \
  -d "{\"username\": \"$USERNAME\", \"password\": \"$PASSWORD\"}")

ACCESS_TOKEN=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access', ''))")

if [ -z "$ACCESS_TOKEN" ]; then
  echo "❌ ÉCHEC: Impossible d'obtenir un token."
  echo "Réponse: $RESPONSE"
  exit 1
fi
echo "✅ Access token obtenu: ${ACCESS_TOKEN:0:40}..."
AUTH_HEADER="Authorization: Bearer $ACCESS_TOKEN"

# ========= 2) USERS =========
print_title "2.1) GET /api/v1/users/ sans auth (doit retourner 401)"
R=$(curl -si "$API/api/v1/users/")
expect "GET /users sans auth" "401" "$R"

print_title "2.2) GET /api/v1/users/ avec auth (doit retourner 200)"
R=$(curl -si "$API/api/v1/users/" -H "$AUTH_HEADER")
expect "GET /users avec auth" "200" "$R"
echo "$R" | tail -1

print_title "2.3) GET /api/v1/users/$MY_USER_ID/ (mon profil, email doit être présent)"
R=$(curl -si "$API/api/v1/users/$MY_USER_ID/" -H "$AUTH_HEADER")
expect "GET /users/me" "200" "$R"
BODY=$(echo "$R" | tail -1)
echo "$BODY"
if echo "$BODY" | grep -q "email"; then
  echo "✅ email présent dans mon profil"
else
  echo "❌ email absent de mon propre profil"
fi

print_title "2.4) GET /api/v1/users/$OTHER_USER_ID/ (autre profil, email NE DOIT PAS être présent)"
R=$(curl -si "$API/api/v1/users/$OTHER_USER_ID/" -H "$AUTH_HEADER")
expect "GET /users/other" "200" "$R"
BODY=$(echo "$R" | tail -1)
echo "$BODY"
if echo "$BODY" | grep -q "email"; then
  echo "❌ SECURITE: email exposé sur un profil tiers !"
else
  echo "✅ email absent du profil tiers"
fi

print_title "2.5) PATCH /api/v1/users/$MY_USER_ID/ (modifier mon profil → 200)"
R=$(curl -si -X PATCH "$API/api/v1/users/$MY_USER_ID/" \
  -H "$AUTH_HEADER" \
  -H "Content-Type: application/json" \
  -d '{"username": "wbekkal"}')
expect "PATCH /users/me" "200" "$R"

print_title "2.6) PATCH /api/v1/users/$OTHER_USER_ID/ (modifier autre profil → 403)"
R=$(curl -si -X PATCH "$API/api/v1/users/$OTHER_USER_ID/" \
  -H "$AUTH_HEADER" \
  -H "Content-Type: application/json" \
  -d '{"username": "hacker_try"}')
expect "PATCH /users/other" "403" "$R"

# ========= 3) MOVIES =========
print_title "3.1) GET /api/v1/movies/ (frontpage, AllowAny → 200)"
R=$(curl -si "$API/api/v1/movies/")
expect "GET /movies sans auth" "200" "$R"
echo "$R" | tail -1

print_title "3.2) GET /api/v1/movies/$TEST_MOVIE_ID/ (détails → 200)"
R=$(curl -si "$API/api/v1/movies/$TEST_MOVIE_ID/" -H "$AUTH_HEADER")
expect "GET /movies/:id" "200" "$R"
echo "$R" | tail -1

# ========= 4) COMMENTS =========
print_title "4.1) GET /api/v1/comments/ sans auth (doit retourner 401)"
R=$(curl -si "$API/api/v1/comments/")
expect "GET /comments sans auth" "401" "$R"

print_title "4.2) GET /api/v1/comments/ avec auth (→ 200)"
R=$(curl -si "$API/api/v1/comments/" -H "$AUTH_HEADER")
expect "GET /comments avec auth" "200" "$R"
echo "$R" | tail -1

print_title "4.3) POST /api/v1/comments/ (créer un commentaire → 201)"
R=$(curl -si -X POST "$API/api/v1/comments/" \
  -H "$AUTH_HEADER" \
  -H "Content-Type: application/json" \
  -d "{\"movie_id\": $TEST_MOVIE_ID, \"content\": \"Super film !\"}")
expect "POST /comments" "201" "$R"
NEW_COMMENT_ID=$(echo "$R" | tail -1 | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null || echo "")
echo "Nouveau comment ID: $NEW_COMMENT_ID"

print_title "4.4) POST /api/v1/movies/$TEST_MOVIE_ID/comments/ (variante → 201)"
R=$(curl -si -X POST "$API/api/v1/movies/$TEST_MOVIE_ID/comments/" \
  -H "$AUTH_HEADER" \
  -H "Content-Type: application/json" \
  -d '{"content": "Commentaire via movie route"}')
expect "POST /movies/:id/comments" "201" "$R"

COMMENT_ID=${NEW_COMMENT_ID:-1}

print_title "4.5) GET /api/v1/comments/$COMMENT_ID/ (→ 200)"
R=$(curl -si "$API/api/v1/comments/$COMMENT_ID/" -H "$AUTH_HEADER")
expect "GET /comments/:id" "200" "$R"
echo "$R" | tail -1

print_title "4.6) PATCH /api/v1/comments/$COMMENT_ID/ (modifier → 200)"
R=$(curl -si -X PATCH "$API/api/v1/comments/$COMMENT_ID/" \
  -H "$AUTH_HEADER" \
  -H "Content-Type: application/json" \
  -d '{"content": "Commentaire édité"}')
expect "PATCH /comments/:id" "200" "$R"

print_title "4.7) DELETE /api/v1/comments/$COMMENT_ID/ (→ 204)"
R=$(curl -si -X DELETE "$API/api/v1/comments/$COMMENT_ID/" -H "$AUTH_HEADER")
expect "DELETE /comments/:id" "204" "$R"

# ========= 5) ROUTES INEXISTANTES =========
print_title "5.1) Route inconnue /api/v1/does-not-exist/ (→ 404)"
R=$(curl -si "$API/api/v1/does-not-exist/" -H "$AUTH_HEADER")
expect "GET /api/v1/unknown" "404" "$R"

print_title "5.2) Route interne exposée /internal/movies/search/ (doit exiger auth → 401)"
R=$(curl -si "$API/internal/movies/search/?q=test")
expect "GET /internal sans auth" "401" "$R"

print_title "5.3) Ancienne route /api/movies/search/ (doit retourner 404)"
R=$(curl -si "$API/api/movies/search/" -H "$AUTH_HEADER")
expect "GET /api/movies/search (hors spec)" "404" "$R"

# ========= 6) SECURITE FORMULAIRES =========
print_title "6.1) Register mot de passe trop court (→ 400)"
R=$(curl -si -X POST "$API/internal/auth/register/" \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","email":"test@test.com","first_name":"T","last_name":"T","password":"short"}')
expect "Register mdp court" "400" "$R"

print_title "6.2) Register email invalide (→ 400)"
R=$(curl -si -X POST "$API/internal/auth/register/" \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","email":"pasunemail","first_name":"T","last_name":"T","password":"Valid1234!"}')
expect "Register email invalide" "400" "$R"

print_title "6.3) Login mauvais credentials (→ 401)"
R=$(curl -si -X POST "$API/oauth/token/" \
  -H "Content-Type: application/json" \
  -d '{"username":"fakeuser","password":"wrongpass"}')
expect "Login mauvais credentials" "401" "$R"

echo
echo "======================================="
echo "Tests terminés."
echo "======================================="