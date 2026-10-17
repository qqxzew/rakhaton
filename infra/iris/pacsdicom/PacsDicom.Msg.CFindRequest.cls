/// C-FIND request sent to the C-FIND business process (T087). Study level query against one simulated PACS.
Class PacsDicom.Msg.CFindRequest Extends Ens.Request
{

/// Application Entity title of the simulated PACS to ask (MOTOL, NNH, HOMOLKA, FNM).
/// The business operation of that PACS is named "CFind.<Target>".
Property Target As %String(MAXLEN = 16);

/// DICOM PatientID (the dataset pseudonym).
Property PatientID As %String(MAXLEN = 64);

/// StudyDate range as DICOM text: YYYYMMDD or YYYYMMDD-YYYYMMDD; empty = any date.
Property StudyDate As %String(MAXLEN = 17);

/// DICOM modality code in ModalitiesInStudy (CT, MR, PT, CR, US, MG, NM); empty = any.
Property Modality As %String(MAXLEN = 16);

Storage Default
{
<Data name="CFindRequestDefaultData">
<Subscript>"CFindRequest"</Subscript>
<Value name="1">
<Value>Target</Value>
</Value>
<Value name="2">
<Value>PatientID</Value>
</Value>
<Value name="3">
<Value>StudyDate</Value>
</Value>
<Value name="4">
<Value>Modality</Value>
</Value>
</Data>
<DefaultData>CFindRequestDefaultData</DefaultData>
<Type>%Storage.Persistent</Type>
}

}
