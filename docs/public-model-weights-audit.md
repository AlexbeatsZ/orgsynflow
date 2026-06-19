# Public Model Weights Audit

Date: 2026-06-20

This document records which OrgSynFlow modules can use official or author-published model weights without local training, and which modules should stay explicit about being heuristic or unavailable.

## Summary

| Module | Public weights/data | Local status | Recommendation |
| --- | --- | --- | --- |
| AiZynthFinder retrosynthesis | Yes. Official docs expose `download_public_data`; Zenodo record `10.5281/zenodo.11430881` contains USPTO ONNX/HDF5 policies, templates, filter model, ringbreaker model, and ZINC stock. | Configured in WSL at `/home/meta/data/aizynthfinder/config.yml`; `uspto_model.onnx`, `uspto_filter_model.onnx`, `uspto_ringbreaker_model.onnx`, templates, and `zinc_stock.hdf5` are present. | Keep as the primary local route-planning engine. |
| ASKCOS retrosynthesis | Yes, but heavy. ASKCOS publishes code and an `askcos-data` repository containing machine learning models and data. The older GitHub repo states model/data are CC BY-NC-SA, not MPL. V2 deployment expects Docker, GitLab repos, and at least 32 GB RAM. | Adapter exists, but no local service is currently confirmed at `ASKCOS_URL`. | Treat as optional external service. Do not block the app on ASKCOS; keep AiZynthFinder as local default. |
| OPERA QSAR | Yes. NIEHS/EPA describe OPERA as a free open-source/open-data QSAR/QSPR model suite. | Installed in WSL at `/home/meta/.local/opt/OPERA2.9`, bridged by `/home/meta/.local/bin/opera`. | Continue using for property/toxicity/ADME-style predictions with applicability-domain notes. |
| RXNMapper atom mapping | Yes. The official `rxn4chemistry/rxnmapper` package uses an unsupervised ALBERT model for atom mapping. | Installed in WSL `orgsynflow-chem` as `rxnmapper 0.4.3`. | Keep using for reaction atom mapping. |
| DRFP reaction features | No weights needed. DRFP is a deterministic differential reaction fingerprint algorithm and explicitly avoids learned fingerprints/training data. | Installed in WSL `orgsynflow-chem` as `drfp 0.3.7`. | Keep as the default reaction feature layer. |
| RXNFP reaction BERT | Public pretrained reaction BERT models exist inside the `rxnfp` library: `bert_pretrained` and `bert_ft`. | Not installed in the current WSL `orgsynflow-chem` environment. | Optional future feature encoder. It is not a drop-in general yield predictor. Installing it may require dependency pinning because the upstream examples target older Python/RDKit stacks. |
| Yield-BERT / reaction yield prediction | Author code and trained-model folders exist in `rxn4chemistry/rxn_yields`, and docs show training regression models from RXNFP base models. The README warns USPTO yield distributions differ by mass scale, limiting applicability. | Not installed/configured. `core/yield_predictor.py` correctly reports no trained yield model. | Do not claim real ML yield prediction yet. If added later, expose it as a narrow-domain model with dataset/source/applicability metadata, not a universal yield oracle. |
| Chemprop | Official Chemprop is an MIT-licensed molecular/reaction property prediction framework. Some application-specific checkpoints exist in papers, but no official generic organic reaction-yield checkpoint was found for direct use. | Not installed/configured. | Keep as a future training/fine-tuning path, not a current public-weight solution. |
| Gaussian/xTB/CREST/PySCF/Psi4/cclib/GoodVibes | Not ML-weight modules. They are quantum chemistry, conformer search, parsing, or thermochemistry tools. | Local/WSL toolchain is already available as documented in `AIREADME.md`. | No training weights required. |

## Source Links

- AiZynthFinder documentation: https://molecularai.github.io/aizynthfinder/
- AiZynthFinder Zenodo model record: https://zenodo.org/records/11430881
- ASKCOS repository: https://github.com/ASKCOS/ASKCOS
- ASKCOS data/model repository: https://github.com/ASKCOS/askcos-data
- ASKCOS v2 docs: https://askcos-docs.mit.edu/guide/1-Introduction/1.1-Introduction.html
- OPERA NIEHS page: https://ntp.niehs.nih.gov/whatwestudy/niceatm/comptox/ct-opera/opera
- RXNMapper repository: https://github.com/rxn4chemistry/rxnmapper
- DRFP repository: https://github.com/reymond-group/drfp
- RXN yield prediction repository: https://github.com/rxn4chemistry/rxn_yields
- RXN yield model training docs: https://rxn4chemistry.github.io/rxn_yields/model_training/
- Chemprop repository: https://github.com/chemprop/chemprop

## Local Evidence

The current WSL AiZynthFinder data directory contains:

```text
/home/meta/data/aizynthfinder/config.yml
/home/meta/data/aizynthfinder/uspto_filter_model.onnx
/home/meta/data/aizynthfinder/uspto_model.onnx
/home/meta/data/aizynthfinder/uspto_ringbreaker_model.onnx
/home/meta/data/aizynthfinder/uspto_ringbreaker_templates.csv.gz
/home/meta/data/aizynthfinder/uspto_templates.csv.gz
/home/meta/data/aizynthfinder/zinc_stock.hdf5
```

The current WSL Python environment reports:

```text
aizynthfinder OK
rxnmapper OK 0.4.3
drfp OK 0.3.7
rxnfp missing
chemprop missing
```

## Installation Boundary

The usable official public artifacts are already configured for AiZynthFinder, OPERA, and RXNMapper. No additional generic yield checkpoint was installed. The official `rxn_yields` instructions target a separate Python 3.6 / RDKit 2020.03.3 environment, and its authors explicitly describe limitations in USPTO yield applicability. Installing it into the current chemistry environment would risk dependency regressions without producing a defensible general yield model.

The Ubuntu WSL subsystem stopped responding during the 2026-06-20 recheck. After the user authorized a global WSL interruption, `WslService` was restarted with administrator privileges and all smoke tests completed successfully.

AiZynthFinder artifact SHA-256 values after recovery:

```text
bd0a3cb74cd7068de474c8fb789a00a66bc42c75636d66510ccac585ebe928f8  uspto_model.onnx
ad29aa32bdfcbe37065045546493806cf04899c55386c438905d83fb14bb6320  uspto_filter_model.onnx
1bf0690352d9e9212d7dbe8b35649caf74f73ef0b30edefdfdac37fce38085be  uspto_ringbreaker_model.onnx
a4f1945e90cfa195538320833d68aed38f14e2fcc2f8afb5d958bc920edcafbe  uspto_templates.csv.gz
5616a056454b10a2f044e69e027422128986856ebd958541a3bf9f837e3a0d14  uspto_ringbreaker_templates.csv.gz
99d39a6f807c3e815487500bafc2b4a9dc66a31af189e3b1776874fb0d4a188d  zinc_stock.hdf5
```

End-to-end verification:

- AiZynthFinder returned two real aspirin routes with `used_fallback=false`.
- RXNMapper 0.4.3 mapped `CCO>>CC=O` with confidence `0.998663`.
- OPERA returned five ethanol QSAR values and applicability-domain flags through the project API.

## Engineering Decision

The route and property modules can rely on public models today: AiZynthFinder for retrosynthesis, OPERA for QSAR properties, and RXNMapper for atom mapping. The yield predictor should remain layered as heuristic plus optional DRFP features until a specific public yield model is installed and its domain is shown in the UI. This avoids presenting a trained-model result where the available public artifacts either require new training/fine-tuning or are too narrow to generalize.
