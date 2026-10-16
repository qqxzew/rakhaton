/// One request for imaging material (state of the request loop, CLAUDE.md 10.2). The FHIR Task
/// with the same id mirrors State; this table is the working state of the production.
Class PacsComparator.Req.Request Extends %Persistent
{

Property RequestId As %String(MAXLEN = 40) [ Required ];

Property ItemId As %String(MAXLEN = 120);

Property CaseId As %String(MAXLEN = 120);

/// Pseudonymous id; used only as FHIR subject of the Task, never in outbound messages.
Property PatientId As %String(MAXLEN = 120);

Property ProviderId As %String(MAXLEN = 60);

Property ProviderName As %String(MAXLEN = 200);

Property ProviderEmail As %String(MAXLEN = 200);

Property ProviderPhone As %String(MAXLEN = 60);

Property ProviderRoute As %String(MAXLEN = 60);

/// Absolute reference to the study at the holding hospital (simulated FHIR endpoint), if located.
Property StudyRef As %String(MAXLEN = 400);

Property Modality As %String(MAXLEN = 20);

/// Comma separated normalized regions (chest,abdomen,...).
Property Regions As %String(MAXLEN = 200);

/// Requested study date, ISO (YYYY-MM-DD, YYYY-MM or YYYY), in the patient's own date frame.
Property TargetDate As %String(MAXLEN = 12);

Property AccessionRef As %String(MAXLEN = 120);

Property Deadline As %String(MAXLEN = 12);

Property State As %String(MAXLEN = 30) [ InitialExpression = "DETECTED" ];

Property ApprovedBy As %String(MAXLEN = 120);

Property ApprovedAt As %String(MAXLEN = 24);

Property SentAt As %String(MAXLEN = 24);

Property Attempts As %Integer [ InitialExpression = 0 ];

Property NextActionAt As %String(MAXLEN = 24);

Property CreatedAt As %String(MAXLEN = 24);

Property UpdatedAt As %String(MAXLEN = 24);

Property FhirTaskId As %String(MAXLEN = 60);

Property ReplyClass As %String(MAXLEN = 30);

Property Note As %String(MAXLEN = 600);

Property VerifyReason As %String(MAXLEN = 600);

/// Comma separated Ens session ids (Visual Trace) of the events of this request.
Property SessionIds As %String(MAXLEN = 4000);

Index RequestIdIdx On RequestId [ Unique ];

Index ItemIdx On ItemId;

Index CaseIdx On CaseId;

Index DueIdx On (State, NextActionAt);

}
