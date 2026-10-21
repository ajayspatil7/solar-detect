# Running the Solar Panel Inspector on a Windows laptop

## One-time setup

1. **Install Python** from https://www.python.org/downloads/windows/ and tick
   **"Add python.exe to PATH"** on the installer's first screen.
2. **Get this folder** onto the laptop, either way:
   - with Git: `git clone https://github.com/ajayspatil7/solar-detect.git`
   - without Git: on the GitHub page, **Code → Download ZIP**, then unzip it
     somewhere simple such as `C:\SolarInspector`.
3. Have the **OpenAI API key** ready. You are asked for it once, on the first
   run; it stays on this laptop in `solar_defect_camera\.env.local`.

## Every time

1. **Turn on the phone hotspot.** On an iPhone: Settings → Personal Hotspot,
   turn on **Allow Others to Join** and **Maximize Compatibility**, and **keep
   that screen open** until the camera has connected. An iPhone hides its
   hotspot from new devices when that screen is closed.
2. **Connect the laptop** to the same hotspot.
3. **Power the camera** by plugging its USB cable into the laptop (or any USB
   charger). Within about 30 seconds its small screen shows **READY** with an
   address starting `172.20.10.`.
4. **Double-click `Start Solar Inspector`.** The first run takes a few minutes
   to set up. If Windows Firewall asks, choose **Allow** on private networks.
5. The **dashboard opens in the browser**. Leave the black launcher window open;
   closing it stops the inspector.

In the dashboard: **Capture and analyze** photographs the panel in front of the
camera and saves the result to the camera's SD card (see **History**).
**Upload image** analyses a photo from the laptop instead.

## Updating

Double-click **`Update Solar Inspector`**. If the folder came from a ZIP, it
opens the download page instead; download the new ZIP and copy
`solar_defect_camera\.env.local` from the old folder into the new one.

## If something is wrong

| You see | Do this |
|---|---|
| Camera screen blank | Unplug and replug USB. On the breadboard rig, check the red and black wires are pushed fully in. |
| Camera screen shows **SETUP** | The camera could not find a known network. Check the hotspot is on with its settings screen open, then replug the camera. |
| Launcher says **CAMERA NOT FOUND** | Make sure the laptop and the camera are on the same hotspot, then press **Find camera** in the dashboard. |
| "Python is not installed" | Install Python as in step 1, ticking "Add python.exe to PATH". |

The camera only works on 2.4 GHz Wi-Fi, which is why **Maximize Compatibility**
must be on for an iPhone hotspot. A new hotspot must be added to the camera
once, over USB, by the developer.
