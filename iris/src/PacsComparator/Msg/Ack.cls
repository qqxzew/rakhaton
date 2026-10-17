Class PacsComparator.Msg.Ack Extends Ens.Response
{

Property Ok As %Boolean [ InitialExpression = 1 ];

Property Info As %String(MAXLEN = 600);

/// Id of the stored Req.Message that holds generated content (e.g. voice audio)
Property MessageId As %String(MAXLEN = 30);

}
