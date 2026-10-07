"""Registry of external datasets used to train the bench models.

Rules (compliance):
* Only datasets whose license allows commercial use and redistribution are
  registered (CC BY 4.0, CC BY-SA 4.0, CC0, public domain). Non-commercial
  (NC) or "research only" datasets are listed in REJECTED with the reason.
* Data is never committed: it is downloaded to $HILBENCH_DATA
  (default ~/.cache/hilbench/datasets).
* `hilbench data verify` checks the license the publisher declares today
  (Zenodo / UCI API) against `license` below and fails on a mismatch.
* Every trained model carries the attribution of its training data in its
  model card (see hilbench/ml/train_real.py).

See docs/datasets.md for the full evaluation, including whether a dataset may
be mirrored on the Hugging Face Hub.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Source:
    id: str
    title: str
    use_case: str
    license: str  # SPDX id
    license_url: str
    homepage: str
    attribution: str
    citation: str
    # where the files come from
    zenodo_record: str | None = None
    uci_id: int | None = None
    urls: tuple[str, ...] = ()
    # only fetch these files from a Zenodo record (prefix match, empty = all)
    zenodo_files: tuple[str, ...] = ()
    # read only these members (glob, max count) out of the archive(s) via HTTP ranges
    zip_members: tuple[tuple[str, int], ...] = ()
    approx_size_mb: int = 0
    # may we mirror the (unmodified or preprocessed) data on the HF Hub?
    hf_rehost: str = "no"  # "yes" | "yes (share-alike)" | "no"
    notes: str = ""
    # non-empty = the publisher's files are currently unusable; download refuses unless forced
    broken: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)


SOURCES: dict[str, Source] = {s.id: s for s in [
    Source(
        id="road",
        title="ROAD - Real ORNL Automotive Dynamometer CAN Intrusion Dataset",
        use_case="CAN bus intrusion detection (fuzzing, fabrication, masquerade, advanced attacks)",
        license="CC-BY-4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        homepage="https://0xsam.com/road/",
        attribution="ROAD dataset by M. Verma, R. Bridges, M. Iannacone, S. Hollifield, P. Moriano, "
                    "S. Hespeler et al., Oak Ridge National Laboratory (CC BY 4.0)",
        citation="Verma et al., 'A comprehensive guide to CAN IDS data and introduction of the ROAD dataset', "
                 "PLOS ONE 19(1), 2024. doi:10.1371/journal.pone.0296879",
        zenodo_record="10462796",
        approx_size_mb=600,
        hf_rehost="yes",
        tags=("can", "security", "automotive"),
    ),
    Source(
        id="can-mirgu",
        title="CAN-MIRGU - CAN bus attack dataset from moving vehicles",
        use_case="CAN bus intrusion detection on a modern vehicle while driving",
        license="CC-BY-4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        homepage="https://archive.ics.uci.edu/dataset/1035/can-mirgu",
        attribution="CAN-MIRGU dataset, UCI Machine Learning Repository, doi:10.24432/C5H911 (CC BY 4.0)",
        citation="CAN-MIRGU, UCI Machine Learning Repository, 2024. doi:10.24432/C5H911",
        uci_id=1035,
        approx_size_mb=500,
        hf_rehost="yes",
        broken="UCI download damaged at the source (checked 2026-10-07): the 520 MB zip has an intact "
               "central directory for one member, but its first ~180 MB (local header + start of the "
               "data) are zero bytes and no local header exists anywhere. Not recoverable; re-check "
               "with `hilbench data download can-mirgu --force`.",
        tags=("can", "security", "automotive"),
    ),
    Source(
        id="speech-commands",
        title="Speech Commands v0.02",
        use_case="keyword spotting / voice control (in-cabin HMI)",
        license="CC-BY-4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        homepage="https://arxiv.org/abs/1804.03209",
        attribution="Speech Commands dataset v0.02 by Pete Warden, Google (CC BY 4.0)",
        citation="P. Warden, 'Speech Commands: A Dataset for Limited-Vocabulary Speech Recognition', "
                 "arXiv:1804.03209, 2018",
        urls=("https://storage.googleapis.com/download.tensorflow.org/data/speech_commands_v0.02.tar.gz",),
        approx_size_mb=2300,
        hf_rehost="yes (already mirrored: google/speech_commands)",
        tags=("audio", "kws"),
    ),
    Source(
        id="uci-har",
        title="Human Activity Recognition Using Smartphones",
        use_case="IMU motion classification (6 activities, accelerometer + gyroscope @50 Hz)",
        license="CC-BY-4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        homepage="https://archive.ics.uci.edu/dataset/240/human+activity+recognition+using+smartphones",
        attribution="Human Activity Recognition Using Smartphones by J. Reyes-Ortiz, D. Anguita, A. Ghio, "
                    "L. Oneto, X. Parra, UCI Machine Learning Repository, doi:10.24432/C54S4K (CC BY 4.0)",
        citation="Anguita et al., 'A Public Domain Dataset for Human Activity Recognition Using Smartphones', "
                 "ESANN 2013",
        uci_id=240,
        approx_size_mb=60,
        hf_rehost="yes",
        tags=("imu", "har"),
    ),
    Source(
        id="mimii",
        title="MIMII - Sound Dataset for Malfunctioning Industrial Machine Investigation and Inspection",
        use_case="anomalous machine-sound detection (pumps, fans, valves, slide rails)",
        license="CC-BY-SA-4.0",
        license_url="https://creativecommons.org/licenses/by-sa/4.0/",
        homepage="https://zenodo.org/records/3384388",
        attribution="MIMII dataset by H. Purohit, R. Tanabe, K. Ichige, T. Endo, Y. Nikaido, K. Suefusa, "
                    "Y. Kawaguchi, Hitachi, Ltd. (CC BY-SA 4.0)",
        citation="Purohit et al., 'MIMII Dataset: Sound Dataset for Malfunctioning Industrial Machine "
                 "Investigation and Inspection', DCASE 2019 Workshop",
        zenodo_record="3384388",
        zenodo_files=("6_dB_fan",),
        zip_members=(("*/id_00/normal/*.wav", 500), ("*/id_00/abnormal/*.wav", 200),
                     ("*/id_02/normal/*.wav", 300), ("*/id_02/abnormal/*.wav", 150)),
        approx_size_mb=2000,
        hf_rehost="yes (share-alike: mirror and derived data must stay CC BY-SA 4.0)",
        notes="Only a sample of the 6 dB fan recordings (machines id_00, id_02) is read out of the "
              "10 GB archive via HTTP range requests.",
        tags=("audio", "anomaly"),
    ),
]}


# Evaluated and rejected (kept here so nobody adds them by accident).
REJECTED: dict[str, str] = {
    "syncan": "ETAS SynCAN: non-commercial use only (custom license terms)",
    "hcrl-car-hacking": "HCRL Car-Hacking/OTIDS: download after registration, no open redistribution license",
    "dcase2021+-task2/toyadmos2": "DCASE 2021+ task 2 / ToyADMOS2: CC BY-NC-SA 4.0 (non-commercial)",
    "dcase2020-task2-dev": "DCASE 2020 task 2 dev set (Zenodo 3678171): Zenodo declares CC BY-NC-SA 4.0 "
                           "(found by `hilbench data verify`, 2026-10-07)",
    "gnss-interference-mendeley": "GNSS interference & spoofing (Mendeley): CC BY-NC (non-commercial)",
    "driverBehaviorDataset (jair-jr)": "GitHub repo without any license (all rights reserved)",
}
