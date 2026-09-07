# Ayurveda mode and Dashavidha provenance

The current non-general departments are Ayurveda specialties: Kayachikitsa,
Panchakarma, Shalya, and Prasuti Tantra. The app therefore uses an Ayurveda
profile for those departments. A future Yoga, Naturopathy, Unani, Siddha, or
Homoeopathy department needs its own clinical profile and must not reuse the
Ayurveda questions merely because all belong to AYUSH.

Every interview begins with the same safety intake: chief complaint, immediate
red-flag checks, medicines, allergies, SOCRATES symptom history, and relevant
past history. Ayurveda mode then records Vikriti, Agni, Nidana, and the parts of
Dashavidha that a patient can reasonably report in conversation.

Dashavidha is separated by provenance:

- Patient conversation: Vikriti, Satmya, Sattva, Ahara Shakti, Vyayama Shakti,
  and Vaya.
- Practitioner confirmation: Prakriti.
- Direct practitioner examination: Sara, Samhanana, and Pramana.

Agni, Koshtha, Nidana, and Panchakarma history remain useful Ayurveda history
fields but are not mislabeled as additional Dashavidha factors.

The LLM and patient APIs cannot write practitioner-controlled fields. A doctor
or administrator enters them through the Physician View. The saved record names
the staff member and time. Confirmed Prakriti is then copied to the patient
registry for future visits; a patient-described body type is never remembered as
a clinical Prakriti assessment.

`patient_reported` means conversational factors have begun to populate.
`partially_confirmed` means a practitioner has recorded examination data while
some of the ten Dashavidha factors remain absent. `practitioner_confirmed` is used
only when Prakriti, Vikriti, all five conversational factors, and all three
examination factors are present.
