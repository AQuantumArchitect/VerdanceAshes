# Cloud BAR shell bakes

Sim locus for living-shell grow → strip dumps.

- Architecture: `outbound/40_CLOUD_BAR_COMPUTE.md`
- **AWS step-by-step (recommended):** `outbound/41_AWS_CLOUD_SETUP.md`
- Yurt peer stub: `ws-win/yurt-sync/board/aws.toml` (Roc substitute)

## Quick path (AWS)

1. Create AWS account + MFA + billing alarms (see outbound 41).
2. Local key + config:

```powershell
powershell -File scripts/cloud/aws/New-BarCloudSshKey.ps1
copy data\cloud\cloud_config.aws.template.json data\cloud\cloud_config.json
# edit host (EC2 public IP), privateKeyPath
```

3. Launch Windows Server 2022 **t3.xlarge**, 100 GB, SG **22+3389 from My IP**.  
   RDP once → run `scripts/cloud/aws/Bootstrap-AwsBarHost.ps1` elevated with your public key.  
   Or: `scripts/cloud/aws/Launch-AwsBarInstance.ps1` after `aws configure`.

4. Connectivity + smoke:

```powershell
powershell -File scripts/cloud/Test-CloudSsh.ps1
powershell -File scripts/cloud/Invoke-CloudShellBake.ps1 -MapIds the_rock_jungle -RefreshMembrane
```

5. **Stop the instance** when idle (disk keeps; no CPU charge).

## Scripts

| Script | Role |
|--------|------|
| `New-CloudBakeBundle.ps1` | Startscripts + queue for 7 maps (BARb rate mixes) |
| `Sync-CloudBarRuntime.ps1` | Push engine, seven maps, BAR.sdd, VerdanceAshes |
| `remote_worker_bake.ps1` | Runs on cloud Windows host |
| `remote_worker_bake.sh` | Optional Linux host (native engine) |
| `Invoke-CloudShellBake.ps1` | Package → sync → run → harvest → strip |
| `Test-CloudSsh.ps1` | SSH + remote dir probe |
| `aws/New-BarCloudSshKey.ps1` | Dedicated ed25519 for cloud |
| `aws/Bootstrap-AwsBarHost.ps1` | OpenSSH + dirs on the EC2 |
| `aws/Launch-AwsBarInstance.ps1` | Optional CLI launch |
| `_cloud_common.ps1` | SSH/SCP + startscript helpers |

## After harvest

Templates land in `data/base_templates/<map>/living_shell_v1.json`.  
Membrane: `outbox/shell_character_membrane.latest.json` (`compute.preferred_locus = cloud`).

## Local headed GPU (no cloud host)

If `cloud_config.json` is missing and headless hangs on IconsAtlas:

```powershell
powershell -File scripts/bake_living_shell_headed.ps1 -MapId the_rock_jungle
```

Same strip contract as harvest; writes `living_shell_v1.json` with `source=bake`.
