/// Entry point of the C-FIND path: a business service without adapter, called in process (T087).
Class PacsDicom.BS.Api Extends Ens.BusinessService
{

Parameter ADAPTER;

/// Seconds to wait for the whole C-FIND (association, query, release).
Property Timeout As %Integer [ InitialExpression = 30 ];

Parameter SETTINGS = "Timeout:Basic";

Method OnProcessInput(pInput As PacsDicom.Msg.CFindRequest, Output pOutput As PacsDicom.Msg.CFindResponse) As %Status
{
	Quit ..SendRequestSync("PacsDicom.BP.CFind", pInput, .pOutput, ..Timeout)
}

}
