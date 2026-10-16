# Label file schema (hand labeling for evaluation)

Labels are made by a teammate by hand and kept **only** under the git-ignored `data/labels/` directory.
Never copy report text, pseudonyms or labeled values into tracked files, tickets or chats.

Target size: 30 to 50 radiology reports for references, 20 clinical notes for planned exams.

## `data/labels/references.csv`

One row per prior study cited by a radiology report. Reports without any citation get one row with
`modality` empty (so that "no reference" is a label too).

| column | meaning | allowed values |
|---|---|---|
| `report_id` | id of the radiology report (`rep-STU-...`) | as in the dataset |
| `modality` | modality of the cited study | `CT`, `MR`, `PET`, `RTG`, `SONO`, `MAMO`, `SCINT`, `UNKNOWN`, or empty |
| `date` | cited date as ISO | `YYYY-MM-DD`, `YYYY-MM`, or empty if no date is written |
| `regions` | normalized regions, `;` separated | `head`, `brain`, `neck`, `chest`, `abdomen`, `pelvis`, `spine`, `extremity`, `breast`, `whole_body`, or empty |
| `site` | hospital or department if the report names one | free text, or empty |
| `note` | optional remark of the labeler | free text |

Rules: label what the report says, not what the dataset contains. A reference to the report's own
study is not a reference. Two-digit years mean 20YY.

## `data/labels/planned_exams.csv`

One row per planned future examination found in a clinical note. Notes without a plan get one row with
`modality` empty.

| column | meaning | allowed values |
|---|---|---|
| `doc_id` | id of the clinical document (`DOC-...`) | as in the dataset |
| `modality` | planned modality | `CT`, `MR`, `PET`, `RTG`, `SONO`, `MAMO`, `SCINT`, `UNKNOWN`, or empty |
| `regions` | normalized regions, `;` separated | as above |
| `date` | explicit date if written | `YYYY-MM-DD` or empty |
| `relative` | relative timing if written | e.g. `3 months`, `6 months`, `2 weeks`, or empty |
| `site` | target hospital or department | free text, or empty |
| `kind` | kind of plan | `imaging`, `rt_planning`, `mdt` |
| `note` | optional remark | free text |

CSV format: `;` separator, UTF-8 (with or without BOM), one header row.
