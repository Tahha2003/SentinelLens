# Sample Data

`bots_sample_events.json` — 600 synthetic BOTS-style security events.

**Composition:**
- 400 noise events (label=0) — normal web traffic, routine logins, AWS API calls
- 200 incident events (label=1) — brute force, lateral movement, C2 beaconing, data exfiltration, malware detection, DNS tunneling

**Attack scenarios:**
| Scenario | Entity | Sourcetype |
|---|---|---|
| Brute force | `wrstock` from `23.22.63.114` → `venus.buttercupgames.com` | wineventlog |
| Lateral movement | `bob` → dc01, fileserver01, appserver02 | wineventlog |
| C2 beaconing | `workstation07` → `185.220.101.45` every ~2 min | stream:http |
| Data exfiltration | `fileserver01` → `104.21.44.102` large TCP transfers | stream:tcp |
| Malware detection | `workstation07`, `workstation12` | symantec:ep:risk:file |
| DNS tunneling | `workstation07` → long hex subdomains | stream:dns |

**Attribution:** Synthetic data generated to match the schema and field conventions of
the [Boss of the SOC v3 dataset](https://github.com/splunk/botsv3) by Splunk.
Not derived from actual BOTS v3 data. Licensed MIT.
