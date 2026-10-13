@font-face{font-family:"Inter";src:url("../fonts/Inter-Variable.woff2") format("woff2");font-weight:100 900;font-display:swap}

:root{
  --bg:#ffffff; --surface:#f8fafc; --border:#dfe7f1;
  --text:#0f172a; --muted:#475569;
  --primary:#0f2a4a; --primary-hover:#173a64; --primary-soft:#eaf3ff; --primary-soft-strong:#dfeeff;
  --accent:#0d9488; --accent-soft:#e8faf6;
  --danger:#b91c1c; --warn:#b45309; --ok:#15803d;
  --radius:10px; --max:1080px;
  --s1:4px; --s2:8px; --s3:16px; --s4:24px; --s5:32px; --s6:48px;
  --font:"Inter",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  --shadow-soft:0 8px 18px rgba(15,42,74,.08);
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;font-family:var(--font);color:var(--text);background:var(--bg);line-height:1.55;font-size:16px}
h1,h2,h3{font-family:var(--font);line-height:1.2;margin:0 0 var(--s3);letter-spacing:-.02em}
h1{font-size:clamp(2rem,5vw,3rem);font-weight:700}
h2{font-size:1.5rem;font-weight:650}
h3{font-size:1.125rem;font-weight:600}
p{margin:0 0 var(--s3);color:var(--muted)}
a{color:var(--primary)}
:focus-visible{outline:3px solid rgba(15,42,74,.38);outline-offset:2px;border-radius:4px;box-shadow:0 0 0 5px rgba(15,42,74,.12)}

.container{max-width:var(--max);margin:0 auto;padding-left:16px;padding-right:16px}
main.container{padding-top:0;padding-bottom:var(--s6)}
main.container>:first-child{margin-top:var(--s5)}
main.container>.hero:first-child{margin-top:0}
.section{padding:var(--s6) 0}

.demo-banner{background:var(--surface);border-bottom:1px solid var(--border);font-size:.8125rem;color:var(--muted);text-align:center;padding:var(--s2) var(--s3)}

html,body{overflow-x:hidden}
.header{border-bottom:1px solid var(--border);background:#fff;position:sticky;top:0;z-index:10}
.header-inner{display:flex;align-items:center;justify-content:space-between;height:64px;position:relative;overflow:hidden}
.logo{font-weight:700;color:var(--text);text-decoration:none;display:flex;align-items:center;gap:var(--s2);min-width:0}
.logo-mark{width:28px;height:28px;border-radius:8px;background:var(--primary);color:#fff;display:grid;place-items:center;font-size:.8rem;flex:none}
.nav-toggle{display:none;min-height:44px;padding:0 var(--s3);border:1px solid var(--border);border-radius:var(--radius);background:#fff;color:var(--text);font:600 .9375rem var(--font);cursor:pointer;transition:background-color .15s,border-color .15s,color .15s,transform .08s}
.nav-toggle:hover{background:var(--surface);border-color:#cbd5e1}
.nav-toggle:focus-visible{background:var(--surface);border-color:#cbd5e1}
.nav-toggle:active{transform:translateY(1px)}
.nav{display:flex;align-items:center;gap:var(--s4)}
.nav a{color:var(--muted);text-decoration:none;font-weight:500;font-size:.9375rem;transition:color .12s ease, transform .12s ease}
.nav a:hover,.nav a[aria-current="page"]{color:var(--text)}

.btn{display:inline-flex;align-items:center;justify-content:center;gap:var(--s2);min-height:44px;padding:0 var(--s4);border-radius:var(--radius);border:1px solid transparent;font:600 .9375rem var(--font);text-decoration:none;cursor:pointer;box-shadow:0 1px 0 rgba(15,42,74,.08);transition:transform .12s ease, box-shadow .12s ease, background-color .12s ease, border-color .12s ease, filter .12s ease}
.btn:hover{filter:brightness(.98)}
.btn:active,.btn.is-pressed,.nav-toggle:active,.nav-toggle.is-pressed,.password-toggle:active,.password-toggle.is-pressed{transform:translateY(1px) scale(.995);box-shadow:inset 0 2px 6px rgba(15,42,74,.12)}
.btn-primary{background:var(--primary);color:#fff}
.btn-primary:hover{background:var(--primary-hover)}
.btn-secondary{background:#fff;color:var(--text);border-color:var(--border)}
.btn-secondary:hover{background:var(--surface)}
.btn-danger{background:var(--danger);color:#fff}
.btn-danger:hover{background:#991b1b}
.btn-block{width:100%}

.hero{padding:48px 0 32px;max-width:680px}
.hero p{font-size:1.125rem}

.card{background:#fff;border:1px solid var(--border);border-radius:var(--radius);padding:var(--s4);box-shadow:0 0 0 1px rgba(148,163,184,.08)}
.grid-3{display:grid;gap:var(--s3);grid-template-columns:repeat(auto-fit,minmax(min(220px,100%),1fr))}
.step{display:flex;gap:var(--s3);align-items:center;min-height:110px}
.step-link{display:flex;gap:var(--s3);align-items:center;min-height:110px;text-decoration:none;color:inherit;cursor:pointer;transition:border-color .12s ease, transform .12s ease, box-shadow .12s ease, background-color .12s ease}
.step-link:hover{border-color:var(--primary);box-shadow:0 8px 22px rgba(15,42,74,.08);transform:translateY(-1px)}
.step-link:focus-visible{border-color:var(--primary);box-shadow:0 0 0 4px rgba(15,42,74,.10)}
.step-link:active{transform:translateY(0);box-shadow:inset 0 2px 8px rgba(15,42,74,.12)}
.step-icon{width:44px;height:44px;border-radius:12px;background:var(--primary-soft);color:var(--primary);border:1px solid var(--primary-soft-strong);display:grid;place-items:center;flex:none;font-weight:700;box-shadow:inset 0 1px 0 rgba(255,255,255,.8)}
.step strong{display:block;font-size:1.05rem}
.step p{margin:4px 0 0;color:var(--muted);font-size:.96rem}

.badge{display:inline-block;padding:2px 10px;border-radius:999px;font-size:.75rem;font-weight:600;background:var(--surface);border:1px solid var(--border);color:var(--muted)}
.badge-ok{background:#dcfce7;color:var(--ok);border-color:#bbf7d0}
.badge-warn{background:#fff7ed;color:var(--warn);border-color:#fed7aa}
.badge-info{background:var(--accent-soft);color:#0f766e;border-color:#99f6e4}

label{display:block;font-weight:600;font-size:.9375rem;margin-bottom:var(--s2)}
input,select,textarea{width:100%;min-height:44px;padding:10px 12px;border:1px solid var(--border);border-radius:var(--radius);font:inherit;color:var(--text);background:#fff}
textarea{min-height:110px;resize:vertical}
.field{margin-bottom:var(--s4)}
.form-section{margin-bottom:var(--s4)}
.form-section>h3{display:flex;gap:var(--s2);align-items:center}

.card img{max-width:100%;height:auto;border-radius:8px;display:block}
.report-card{display:flex;gap:var(--s3);align-items:center;text-decoration:none;color:inherit}
.card.report-card img{width:72px;height:72px;object-fit:cover;border-radius:8px;border:1px solid var(--border);flex:none;max-width:none}

.flash{padding:var(--s3);border-radius:var(--radius);border:1px solid var(--border);background:var(--surface);margin-bottom:var(--s3)}
.empty{text-align:center;padding:var(--s6) var(--s3);border:1px dashed var(--border);border-radius:var(--radius)}

.footer{border-top:1px solid var(--border);padding:var(--s5) 0;color:var(--muted);font-size:.875rem}

@media(max-width:640px){
  .nav-toggle{display:inline-flex;align-items:center}
  .header-inner{flex-wrap:nowrap;height:64px;overflow:visible}
  .nav{display:none;position:absolute;top:64px;left:0;right:0;flex-direction:column;align-items:stretch;gap:0;background:#fff;border-bottom:1px solid var(--border);padding:var(--s2) var(--s3) var(--s3);box-shadow:var(--shadow-soft)}
  .header.is-open .nav{display:flex}
  .nav a,.nav .btn,.nav form{width:100%}
  .section{padding:var(--s5) 0}
  .sticky-submit{position:sticky;bottom:0;background:#fff;padding:var(--s3) 0;border-top:1px solid var(--border)}
}

.skip-link{position:absolute;left:-999px;top:0;background:var(--primary);color:#fff;padding:var(--s2) var(--s3)}
.skip-link:focus{left:var(--s3);top:var(--s3);z-index:20}
.nav form{margin:0}
.flash-error{background:#fff1f2;border-color:#fecdd3;color:var(--danger)}
.flash-ok{background:#dcfce7;border-color:#bbf7d0;color:var(--ok)}
.stepper{display:flex;flex-wrap:wrap;gap:var(--s2);list-style:none;padding:0;margin:0 0 var(--s4)}
.stepper .is-current{background:var(--primary);color:#fff;border-color:var(--primary)}
.photo-pair{display:grid;grid-template-columns:1fr 1fr;gap:var(--s3);margin:var(--s4) 0}
.timeline{list-style:none;padding:0;margin:0;display:grid;gap:var(--s2)}
.map-frame{height:280px;min-height:280px;border:1px solid var(--border);border-radius:var(--radius);background:var(--surface);overflow:hidden}
.leaflet-container.map-frame{height:280px}
.consent{display:flex;gap:var(--s2);align-items:flex-start;font-weight:500;margin:0 0 var(--s3)}
.consent input{width:auto;min-height:20px;margin-top:4px}
.preview{display:none;max-width:100%;max-height:180px;height:auto;border-radius:8px;border:1px solid var(--border);margin-top:var(--s2)}
.card img.preview{display:none}
.card img.preview.is-visible{display:block}
.narrow{max-width:440px;margin:var(--s5) auto}
.stack{display:grid;gap:var(--s3)}
.hero .btn{margin-right:var(--s2);margin-bottom:var(--s2)}
.password-wrap{position:relative}
.password-wrap input{padding-right:4.5rem}
.password-toggle{position:absolute;right:6px;top:50%;transform:translateY(-50%);min-height:36px;padding:0 var(--s2);border:0;background:transparent;color:var(--muted);font:600 .8125rem var(--font);cursor:pointer;border-radius:8px;transition:background-color .12s ease, color .12s ease, transform .12s ease}
.password-toggle:hover{background:var(--surface);color:var(--text)}
.password-toggle.is-pressed{transform:translateY(-50%) scale(.98)}
@media(max-width:640px){
  .photo-pair{grid-template-columns:1fr}
}
@media (prefers-reduced-motion: reduce){
  *,*::before,*::after{scroll-behavior:auto!important;transition:none!important;animation:none!important}
}

