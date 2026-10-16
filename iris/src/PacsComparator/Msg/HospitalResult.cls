Class PacsComparator.Msg.HospitalResult Extends Ens.Response
{

Property Found As %Boolean [ InitialExpression = 0 ];

Property Modality As %String(MAXLEN = 20);

Property StudyDate As %String(MAXLEN = 12);

Property StudyRef As %String(MAXLEN = 400);

Property DocumentId As %String(MAXLEN = 80);

Property Note As %String(MAXLEN = 400);

}
