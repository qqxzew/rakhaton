/// Time helpers. All timestamps are UTC "YYYY-MM-DD hh:mm:ss" strings. The demo clock can be moved
/// forward ("advance time") without waiting: Now() is the real UTC time plus a stored offset.
Class PacsComparator.Req.Util Extends %RegisteredObject
{

ClassMethod OffsetSeconds() As %Integer
{
	Quit +$Get(^PacsComparator.Clock("offset"))
}

ClassMethod Now() As %String
{
	Quit ..Shift($ZTIMESTAMP, ..OffsetSeconds())
}

ClassMethod AddSeconds(ts As %String, secs As %Integer) As %String
{
	Quit ..Shift($ZDATETIMEH(ts, 3), secs)
}

ClassMethod Shift(h As %String, secs As %Integer) As %String
{
	Set d = $Piece(h, ",", 1), s = $Piece($Piece(h, ",", 2), ".", 1) + secs
	Set d = d + (s \ 86400), s = s # 86400
	Quit $ZDATETIME(d _ "," _ s, 3)
}

/// FHIR instant for a stored timestamp.
ClassMethod Iso(ts As %String) As %String
{
	Quit $Translate($Extract(ts, 1, 19), " ", "T") _ "Z"
}

}
