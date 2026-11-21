#!/bin/sh
# Builds the website version into ./web-dist, ready for GitHub Pages at /onepiece-restock/
set -e
# Public connection details (safe to publish: the publishable key only allows what the row rules allow)
export EXPO_PUBLIC_SUPABASE_URL="${EXPO_PUBLIC_SUPABASE_URL:-https://drcrswtieglukyfgotgj.supabase.co}"
export EXPO_PUBLIC_SUPABASE_ANON_KEY="${EXPO_PUBLIC_SUPABASE_ANON_KEY:-sb_publishable_QnzxIZSLZgBLS13xNo2png_JMYeP7FB}"
rm -rf web-dist
CI=1 npx expo export --platform web --output-dir web-dist
python3 - <<'PY'
p='web-dist/index.html'; s=open(p).read()
tags=('<meta name="apple-mobile-web-app-capable" content="yes">'
 '<meta name="mobile-web-app-capable" content="yes">'
 '<meta name="apple-mobile-web-app-status-bar-style" content="black">'
 '<meta name="apple-mobile-web-app-title" content="OP Market">'
 '<meta name="theme-color" content="#0a0d0b">'
 '<link rel="apple-touch-icon" href="/onepiece-restock/apple-touch-icon.png">'
 '<link rel="manifest" href="/onepiece-restock/manifest.json">'
 '<style>html,body{background:#0a0d0b}</style>')
s=s.replace('</head>', tags+'</head>',1)
s=s.replace('content="width=device-width, initial-scale=1, shrink-to-fit=no"','content="width=device-width, initial-scale=1, viewport-fit=cover"')
open(p,'w').write(s); open('web-dist/404.html','w').write(s); open('web-dist/.nojekyll','w').write('')
PY
