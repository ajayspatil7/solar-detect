#pragma once

// Wi-Fi provisioning for a camera that travels to someone else's network.
//
// Credentials live in NVS, not in compiled firmware, so the board can be moved
// between locations by a non-technical operator. If nothing is stored, or the
// stored network cannot be joined, the firmware raises its own access point and
// serves the page below; the OLED tells the operator what to connect to.
//
// secrets.h is still honoured as a fallback so a developer's own board keeps
// working without provisioning.

#include <Arduino.h>
#include <Preferences.h>
#include <WiFi.h>

namespace provisioning {

constexpr char NAMESPACE[] = "solarcam";
constexpr char AP_SSID[] = "SOLAR-SETUP";
constexpr char AP_PASSWORD[] = "";  // open network; nothing sensitive is served
constexpr uint32_t CONNECT_TIMEOUT_MS = 20000;

struct Credentials {
  String ssid;
  String password;
  // True once the operator has saved or cleared a network on this board. From
  // then on the compiled secrets.h fallback is ignored, so "forget" cannot
  // silently rejoin whichever network the firmware was built against.
  bool configured = false;
};

inline Credentials load() {
  Credentials c;
  Preferences prefs;
  if (!prefs.begin(NAMESPACE, true)) return c;
  c.configured = prefs.getBool("configured", false);
  c.ssid = prefs.getString("ssid", "");
  c.password = prefs.getString("pass", "");
  prefs.end();
  return c;
}

inline bool save(const String &ssid, const String &password) {
  Preferences prefs;
  if (!prefs.begin(NAMESPACE, false)) return false;
  const bool ok = prefs.putString("ssid", ssid) > 0;
  prefs.putString("pass", password);
  prefs.putBool("configured", true);
  prefs.end();
  return ok;
}

// Forgets the network but keeps the board under operator control, so the next
// boot goes to the setup portal rather than back to the build-time fallback.
inline void clear() {
  Preferences prefs;
  if (!prefs.begin(NAMESPACE, false)) return;
  prefs.putString("ssid", "");
  prefs.putString("pass", "");
  prefs.putBool("configured", true);
  prefs.end();
}

// Percent-decoding keeps Wi-Fi passwords intact whatever characters they use;
// the setup page posts application/x-www-form-urlencoded for exactly this reason.
inline String urlDecode(const String &value) {
  String out;
  out.reserve(value.length());
  for (size_t i = 0; i < value.length(); ++i) {
    const char c = value[i];
    if (c == '+') {
      out += ' ';
    } else if (c == '%' && i + 2 < value.length()) {
      const char hex[3] = {value[i + 1], value[i + 2], '\0'};
      out += static_cast<char>(strtol(hex, nullptr, 16));
      i += 2;
    } else {
      out += c;
    }
  }
  return out;
}

inline String formField(const String &body, const String &key) {
  const String needle = key + "=";
  int start = body.startsWith(needle) ? 0 : body.indexOf("&" + needle);
  if (start < 0) return "";
  if (start > 0) start += 1;
  start += needle.length();
  int end = body.indexOf('&', start);
  if (end < 0) end = body.length();
  return urlDecode(body.substring(start, end));
}

const char SETUP_HTML[] PROGMEM = R"HTML(<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Solar Inspector setup</title><style>
:root{color-scheme:light}
*{box-sizing:border-box}
body{margin:0;background:#f5f3ee;color:#292c32;
 font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main{max-width:420px;margin:0 auto;padding:24px 18px 48px}
h1{font-size:1.35rem;margin:0 0 4px}
p.sub{margin:0 0 22px;color:#74747b;font-size:.94rem}
label{display:block;font-weight:600;font-size:.88rem;margin:16px 0 6px}
select,input,button{width:100%;font:inherit;padding:12px;border-radius:10px;
 border:1px solid #dedad2;background:#fffdfa;color:#292c32}
button{margin-top:22px;border:0;background:#557fc4;color:#fff;font-weight:700;cursor:pointer}
button:disabled{opacity:.55;cursor:wait}
#msg{margin-top:16px;padding:12px;border-radius:10px;display:none;font-size:.92rem}
.ok{background:#e6f0e9;color:#2f6b48;display:block!important}
.bad{background:#f7e6e4;color:#96412f;display:block!important}
.busy{background:#eef2f8;color:#3e5b8a;display:block!important}
small{color:#74747b;font-size:.82rem}
</style></head><body><main>
<h1>Connect the camera to Wi-Fi</h1>
<p class="sub">Turn the phone hotspot on first, then enter its password below.
The camera restarts and joins automatically. Only needed once per location.</p>

<label for="ssid">Network</label>
<select id="ssid"><option value="">Scanning…</option></select>

<label for="manual">Or type the name yourself</label>
<input id="manual" value="Krutika’s iPhone 14" placeholder="Network name" autocomplete="off">

<label for="pass">Password</label>
<input id="pass" type="password" placeholder="Wi-Fi password" autocomplete="off">

<button id="save">Save and restart</button>
<div id="msg"></div>
<p><small>The camera needs a 2.4 GHz network. It cannot join 5 GHz-only Wi-Fi.</small></p>
</main><script>
const $=id=>document.getElementById(id);
function note(text,kind){const m=$('msg');m.textContent=text;m.className=kind}
// The demo always runs on one hotspot. If the scan sees it, select the exact
// scanned name -- iOS device names use a typographic apostrophe, so a hand-typed
// ASCII one would silently fail to match.
const TARGET='Krutika’s iPhone 14';
const norm=s=>s.replace(/[\u2018\u2019\u02bc']/g,"'").toLowerCase().trim();
async function scan(){
  try{
    const r=await fetch('/scan');const nets=await r.json();
    const sel=$('ssid');sel.innerHTML='';
    if(!nets.length){sel.innerHTML='<option value="">No networks found</option>';return}
    nets.forEach(n=>{const o=document.createElement('option');
      o.value=n.ssid;o.textContent=`${n.ssid}  (${n.rssi} dBm)`;sel.appendChild(o)});
    const match=nets.find(n=>norm(n.ssid)===norm(TARGET));
    if(match){sel.value=match.ssid;$('manual').value='';
      note('Found '+match.ssid+'. Just enter the password below.','ok')}
  }catch(e){note('Could not scan for networks. Reload the page.','bad')}
}
$('save').addEventListener('click',async()=>{
  const ssid=($('manual').value||$('ssid').value).trim();
  const pass=$('pass').value;
  if(!ssid){note('Choose a network or type its name.','bad');return}
  $('save').disabled=true;note('Saving and restarting the camera…','busy');
  try{
    await fetch('/wifi',{method:'POST',
      headers:{'Content-Type':'application/x-www-form-urlencoded'},
      body:'ssid='+encodeURIComponent(ssid)+'&pass='+encodeURIComponent(pass)});
    note('Saved. The camera is restarting — this page will stop responding, '
       + 'which is expected. Reconnect your device to '+ssid+', then watch the '
       + 'small screen on the camera for its address.','ok');
  }catch(e){
    note('Saved. The camera is restarting. Reconnect to '+ssid+' and check the '
       + 'camera screen for its address.','ok');
  }
});
scan();
</script></body></html>
)HTML";

}  // namespace provisioning
