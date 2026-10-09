# mobility-security-ml (archived)

This repository is archived. Its content moved to **https://github.com/mhabedank/mobility-model-zoo** on 2026-10-09 (pull request #9), with its full git history.

| Former content | New location in mobility-model-zoo |
|---|---|
| Research notes (`docs/research/`) | `topics/security/research/` (translated to English; merge log in `merge-log.md`) |
| `can-ids-tiny` (random forest CAN intrusion detector) | model `picket-forest`: code `src/mobility_model_zoo/security/can_ids/`, firmware `firmware/picket-forest/`, results `topics/security/reports/picket-forest/` |
| HIL bench `hilbench` | `src/mobility_model_zoo/edge/` (CLI `edge`), firmware `firmware/bench/`, inventory `hil/` |
| Dataset registry and downloader | `src/mobility_model_zoo/datasets/`, declarations in `topics/*/compliance/datasets.yaml`, CLI `zoo data` |
| Edge models `can_ids_road`, `mimii_fan_ae`, `har_cnn1d` | models `picket-mlp`, `hum-fan`, `pace-cnn` (topics `security` and `condition-monitoring`) |

The branches `claude/clever-goldberg-ygio83` and `claude/cool-volta-rqsgdx` stay readable here. New work happens in mobility-model-zoo only.
