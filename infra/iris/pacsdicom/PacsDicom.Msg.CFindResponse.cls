/// Result of a C-FIND (T087): matches as a JSON array of {accession, studyDate, modalities, description, studyUid}.
Class PacsDicom.Msg.CFindResponse Extends Ens.Response
{

/// OK, or ERROR when the association or the query failed.
Property Outcome As %String(MAXLEN = 16);

Property Message As %String(MAXLEN = 500);

Property MatchCount As %Integer;

Property MatchesJson As %String(MAXLEN = "");

Storage Default
{
<Data name="CFindResponseDefaultData">
<Subscript>"CFindResponse"</Subscript>
<Value name="1">
<Value>Outcome</Value>
</Value>
<Value name="2">
<Value>Message</Value>
</Value>
<Value name="3">
<Value>MatchCount</Value>
</Value>
<Value name="4">
<Value>MatchesJson</Value>
</Value>
</Data>
<DefaultData>CFindResponseDefaultData</DefaultData>
<Type>%Storage.Persistent</Type>
}

}
