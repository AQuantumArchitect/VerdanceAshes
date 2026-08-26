# Outbound 41 — AWS remote compute for BAR + yurt

**Date:** 2026-07-28  
**Status:** Guided setup — account creation is on Luke; scaffolding is ready  
**Extends:** [40](40_CLOUD_BAR_COMPUTE.md)  
**Also serves:** yurt mesh (stand-in for **Roc** while host/bridge are unreliable)

---

## Why AWS (instead of waiting on Roc)

| Need | Roc (home box) | AWS Windows EC2 |
|------|----------------|-----------------|
| BAR headless grow/strip | Offline / bridge dark often | Always rentable, kill when done |
| spring-headless.exe + BARb parity | Yes (Windows) | Yes (Windows Server AMI) |
| Multi-hour unattended sims | Depends on home power/net | Yes |
| Yurt bridge / remote jobs | Intended muscle | Same role as **substitute node `aws`** |
| Cost | Electricity only | ~\$0.15–0.40/hr Windows mid-size; **stop when idle** |

**Sim locus = cloud.** Authoring, strip, membrane, campaign stay on Wargen.

---

## What we are building

```
LOCAL (Wargen)
  data/cloud/cloud_config.json     → points at EC2 public IP (or Tailscale later)
  scripts/cloud/Invoke-CloudShellBake.ps1
  yurt inventory: node "aws"

AWS EC2  (Windows Server 2022)
  OpenSSH Server :22
  C:\verdance_cloud\bar_data\...   engine + 7 maps + BAR.sdd + VerdanceAshes
  C:\yurt\...                      optional yurt-bridge later
  remote_worker_bake.ps1           living-shell grow jobs
```

Phase 1 (this doc): **account → Windows VM → SSH → BAR smoke bake**.  
Phase 2 (later): Tailscale + yurt-bridge + Syncthing so `aws` is a full mesh peer like Roc.

---

## Cost honesty (read before launch)

- New AWS accounts often get **Free Tier credits** (order of \$100–\$200). Check [aws.amazon.com/free](https://aws.amazon.com/free/).
- **Windows + 16 GB RAM is not “free forever.”** Expect roughly:
  - **t3.xlarge** (4 vCPU / 16 GB): order of **\$0.20–0.35/hr** Windows on-demand (region-dependent).
  - **100 GB gp3 disk:** a few dollars/month.
  - **Data transfer out:** small for harvest; one-time **~4 GB upload** of BAR runtime.
- **Rule:** after a bake, **Stop** the instance (disk keeps; no CPU charge). **Terminate** only when you no longer need the box.
- Set a **billing alarm** at \$20 and \$50 on day one.

Recommended first box:

| Knob | Value |
|------|--------|
| Region | `us-east-1` or closest to you |
| AMI | **Microsoft Windows Server 2022 Base** |
| Instance | **t3.xlarge** (or **c6i.xlarge** if available/cheaper for CPU) |
| Storage | **100 GB gp3** (OS + BAR.sdd ~3.2 GB + maps + headroom) |
| Network | Public IP for first SSH; security group **22 from YOUR IP only** |
| Spot? | Optional later to cut cost; on-demand is simpler for first setup |

**Do not use t2.micro / t3.micro for BAR** — not enough RAM for spring-headless + content.

---

## Step-by-step (we do this together)

### STEP 1 — Create the AWS account (you, in browser)

1. Open: https://portal.aws.amazon.com/billing/signup  
2. Use an email you control; pick a strong root password.  
3. Account type: **Personal**.  
4. Enter payment card (required for verification; free-tier / credits apply first).  
5. Phone verification.  
6. Support plan: **Basic (free)**.  
7. Sign in to the **AWS Management Console**: https://console.aws.amazon.com/

**Security before anything else (10 minutes):**

1. Search console for **IAM** → **Users** → create user `luke-admin` with **AdministratorAccess** (or use IAM Identity Center later).  
2. Enable **MFA** on the root account (IAM → Dashboard → “Add MFA”).  
3. Do **not** use the root user for daily work after this.  
4. **Billing → Budgets** → create budget alert at **\$20** and **\$50**.

When this is done, tell me: **“account ready”** (and which **region** you picked).

---

### STEP 2 — Install AWS CLI + make a BAR SSH key (local, we can automate)

On Wargen (PowerShell):

```powershell
# AWS CLI v2 (if missing)
winget install -e --id Amazon.AWSCLI

# Dedicated key for BAR cloud (do not reuse GitHub keys for cloud if avoidable)
powershell -File "C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace\scripts\cloud\aws\New-BarCloudSshKey.ps1"
```

Then configure credentials (from IAM user access key, or SSO):

```powershell
aws configure
# AWS Access Key ID / Secret
# Default region: us-east-1  (or yours)
# Default output: json
```

---

### STEP 3 — Launch Windows EC2 + open SSH

**Console path (manual, recommended first time):**

1. EC2 → **Launch instance**  
2. Name: `verdance-bar-bake`  
3. AMI: **Windows Server 2022 Base**  
4. Instance type: **t3.xlarge**  
5. Key pair: create new `verdance-bar-aws` (download `.pem` — keep safe) **or** use the public key from Step 2  
6. Network:  
   - Allow **RDP 3389** from **My IP** (first login / OpenSSH install)  
   - Allow **SSH 22** from **My IP**  
7. Storage: **100 GiB gp3**  
8. Launch → wait **Running** + **2/2 status checks**

**Get the Administrator password** (EC2 → instance → Connect → RDP → Decrypt password with the `.pem`).

---

### STEP 4 — On the Windows VM (RDP once)

Run in **Administrator PowerShell** on the instance (or push via our bootstrap script after OpenSSH is up):

```powershell
# Or: copy scripts/cloud/aws/Bootstrap-AwsBarHost.ps1 to the box and run it
powershell -ExecutionPolicy Bypass -File C:\Bootstrap-AwsBarHost.ps1
```

That script:

- Installs / enables **OpenSSH Server**
- Opens firewall for SSH
- Creates `C:\verdance_cloud\{bar_data,jobs,results,scripts}`
- Installs your **public key** for `Administrator` (or a dedicated user)
- Optional: installs **Tailscale** for yurt mesh Phase 2

After SSH works, you can **close RDP** and work only from Wargen.

---

### STEP 5 — Point Verdance at the box

```powershell
cd "C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace"
copy data\cloud\cloud_config.template.json data\cloud\cloud_config.json
# edit host = EC2 public IPv4, user = Administrator, privateKeyPath = your .pem or id path
```

Or fill from the AWS template:

```powershell
copy data\cloud\cloud_config.aws.template.json data\cloud\cloud_config.json
```

Smoke:

```powershell
powershell -File scripts\cloud\Test-CloudSsh.ps1
powershell -File scripts\cloud\Invoke-CloudShellBake.ps1 -MapIds the_rock_jungle -RefreshMembrane
```

Full seven maps after Jungle is green:

```powershell
powershell -File scripts\cloud\Invoke-CloudShellBake.ps1 -RefreshMembrane
```

---

### STEP 6 — Register as yurt node `aws` (Roc stand-in)

Inventory + board stubs live under:

- `ws-win/yurt/inventory.yaml` → node `aws`
- `ws-win/yurt-sync/board/aws.toml`
- `ws-win/yurt-sync/nodes.d/aws.toml` (or `nodes.toml` peer block)

Phase 1 capability: **BAR headless jobs via SSH** (Verdance scripts).  
Phase 2: install **Tailscale** on EC2, run **yurt-bridge :8787**, publish `work/_aws/bridge-client.toml` — same five join steps as Roc (`yurt-bridge/docs/JOIN.md`).

Roc-deferred work that can use AWS **now** (no Roc needed):

| Work | How on AWS |
|------|------------|
| Living-shell BAR bakes (all 7 maps) | `Invoke-CloudShellBake.ps1` |
| Headless BAR smoke / IconsAtlas isolation | same |

**Local free alternative (no AWS money seal):** headed GPU bake on Wargen:

```powershell
powershell -File scripts/bake_living_shell_headed.ps1 -MapId the_rock_jungle
```

See [40](40_CLOUD_BAR_COMPUTE.md) § Local headed GPU path.
| Long unattended Windows CPU jobs | SSH + scheduled task / remote_worker |
| Later: yurt `jobs` allowlist | after bridge on `aws` |

Still better on real Roc (GPU): Ollama larger models, CUDA training, grok-hands GPU seats.

---

## Files in this drop

| Path | Role |
|------|------|
| `outbound/41_AWS_CLOUD_SETUP.md` | This guide |
| `data/cloud/cloud_config.aws.template.json` | AWS-flavored cloud_config |
| `scripts/cloud/aws/New-BarCloudSshKey.ps1` | Local ed25519 key for BAR cloud |
| `scripts/cloud/aws/Bootstrap-AwsBarHost.ps1` | Run on the EC2 (Admin) |
| `scripts/cloud/aws/Launch-AwsBarInstance.ps1` | Optional CLI launch (after AWS CLI + key) |
| `scripts/cloud/Test-CloudSsh.ps1` | SSH connectivity check |
| `scripts/cloud/README.md` | Updated quick path |
| yurt inventory / board `aws` | Mesh registration stubs |

---

## Success criteria

1. SSH from Wargen: `ssh -i <key> Administrator@<public-ip> hostname`  
2. Jungle cloud bake produces `VA_SHELL_UNIT` lines → `living_shell_v1.json`  
3. Instance **Stopped** when not baking (billing alarm quiet)  
4. Yurt board lists `aws` as compute substitute for Roc-class CPU work  

---

## Operator checklist (print this)

- [ ] AWS account + MFA + billing alarms  
- [ ] IAM user / access keys (or SSO)  
- [ ] Region chosen  
- [ ] Key pair / `New-BarCloudSshKey.ps1`  
- [ ] EC2 Windows t3.xlarge + 100 GB + SG 22+3389 My IP  
- [ ] RDP → Bootstrap-AwsBarHost.ps1  
- [ ] `cloud_config.json` filled  
- [ ] `Test-CloudSsh.ps1` green  
- [ ] Jungle bake smoke  
- [ ] Stop instance  
- [ ] (Optional) Tailscale + yurt-bridge as node `aws`  
