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
constexpr char AP_ADDRESS[] = "192.168.4.1";

// Unplugging and replugging the camera this many times, each within the window
// below, forces setup mode. It is the only way to re-provision a camera that is
// still happily connected to an old network that remains in range, and it needs
// no buttons, wires or serial cable.
constexpr uint8_t RESET_REPLUGS = 3;
constexpr uint32_t RESET_WINDOW_MS = 8000;

// Up to MAX_NETWORKS are remembered, most recently saved first, so the camera
// can move between known places -- home, office, a client's hotspot -- without
// being re-provisioned each time.
constexpr uint8_t MAX_NETWORKS = 5;

struct Network {
  String ssid;
  String password;
};

struct SavedNetworks {
  Network items[MAX_NETWORKS];
  uint8_t count = 0;
  // True once the operator has saved or cleared a network on this board. From
  // then on the compiled secrets.h fallback is ignored, so "forget" cannot
  // silently rejoin whichever network the firmware was built against.
  bool configured = false;
};

inline void keyName(char *out, size_t size, const char *prefix, uint8_t index) {
  snprintf(out, size, "%s%u", prefix, static_cast<unsigned>(index));
}

inline SavedNetworks load() {
  SavedNetworks saved;
  Preferences prefs;
  if (!prefs.begin(NAMESPACE, true)) return saved;
  saved.configured = prefs.getBool("configured", false);
  const uint8_t count = prefs.isKey("count") ? prefs.getUChar("count", 0) : 0;
  for (uint8_t i = 0; i < count && i < MAX_NETWORKS; ++i) {
    char ssidKey[16], passKey[16];
    keyName(ssidKey, sizeof(ssidKey), "ssid", i);
    keyName(passKey, sizeof(passKey), "pass", i);
    if (!prefs.isKey(ssidKey)) continue;
    const String ssid = prefs.getString(ssidKey, "");
    if (ssid.isEmpty()) continue;
    saved.items[saved.count++] = {ssid, prefs.isKey(passKey) ? prefs.getString(passKey, "") : String()};
  }
  // Boards provisioned by the previous firmware stored exactly one network.
  if (saved.count == 0 && prefs.isKey("ssid")) {
    const String legacy = prefs.getString("ssid", "");
    if (!legacy.isEmpty()) {
      saved.items[saved.count++] = {legacy, prefs.isKey("pass") ? prefs.getString("pass", "") : String()};
    }
  }
  prefs.end();
  return saved;
}

inline bool writeAll(const SavedNetworks &saved) {
  Preferences prefs;
  if (!prefs.begin(NAMESPACE, false)) return false;
  for (uint8_t i = 0; i < MAX_NETWORKS; ++i) {
    char ssidKey[16], passKey[16];
    keyName(ssidKey, sizeof(ssidKey), "ssid", i);
    keyName(passKey, sizeof(passKey), "pass", i);
    if (i < saved.count) {
      prefs.putString(ssidKey, saved.items[i].ssid);
      prefs.putString(passKey, saved.items[i].password);
    } else {
      if (prefs.isKey(ssidKey)) prefs.remove(ssidKey);
      if (prefs.isKey(passKey)) prefs.remove(passKey);
    }
  }
  prefs.putUChar("count", saved.count);
  prefs.putBool("configured", true);
  if (prefs.isKey("ssid")) prefs.remove("ssid");
  if (prefs.isKey("pass")) prefs.remove("pass");
  prefs.end();
  return true;
}

// Saving a network moves it to the front; the oldest drops off when full.
inline bool save(const String &ssid, const String &password) {
  const SavedNetworks current = load();
  SavedNetworks next;
  next.items[next.count++] = {ssid, password};
  for (uint8_t i = 0; i < current.count && next.count < MAX_NETWORKS; ++i) {
    if (current.items[i].ssid != ssid) next.items[next.count++] = current.items[i];
  }
  return writeAll(next);
}

// Forgets the network but keeps the board under operator control, so the next
// boot goes to the setup portal rather than back to the build-time fallback.
inline uint8_t registerBoot() {
  Preferences prefs;
  if (!prefs.begin(NAMESPACE, false)) return 0;
  const uint8_t boots = prefs.getUChar("boots", 0) + 1;
  prefs.putUChar("boots", boots);
  prefs.end();
  return boots;
}

inline void clearBootCount() {
  Preferences prefs;
  if (!prefs.begin(NAMESPACE, false)) return;
  prefs.putUChar("boots", 0);
  prefs.end();
}

inline void clear() {
  writeAll(SavedNetworks{});
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
<p class="sub">Choose the same Wi-Fi your laptop uses and enter its password. The
camera restarts and joins it. The Solar Inspector launcher on the laptop can do
this for you automatically.</p>

<label for="ssid">Network</label>
<select id="ssid"><option value="">Scanning…</option></select>

<label for="manual">Or type the name yourself</label>
<input id="manual" placeholder="Network name" autocomplete="off">

<label for="pass">Password</label>
<input id="pass" type="password" placeholder="Wi-Fi password" autocomplete="off">

<button id="save">Save and restart</button>
<div id="msg"></div>
<p><small>The camera needs a 2.4 GHz network. It cannot join 5 GHz-only Wi-Fi.</small></p>
</main><script>
const $=id=>document.getElementById(id);
function note(text,kind){const m=$('msg');m.textContent=text;m.className=kind}
async function scan(){
  try{
    const r=await fetch('/scan');const nets=await r.json();
    const sel=$('ssid');sel.innerHTML='';
    if(!nets.length){sel.innerHTML='<option value="">No networks found</option>';return}
    nets.forEach(n=>{const o=document.createElement('option');
      o.value=n.ssid;o.textContent=`${n.ssid}  (${n.rssi} dBm)`;sel.appendChild(o)});
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
