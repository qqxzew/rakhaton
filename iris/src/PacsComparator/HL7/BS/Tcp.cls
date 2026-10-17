Include Ensemble

/// HL7 v2 from the simulated RIS over MLLP (TCP, port 4561 inside the IRIS container).
/// Immediate ACK; the message goes on to the routing process.
Class PacsComparator.HL7.BS.Tcp Extends EnsLib.HL7.Service.TCPService
{

Parameter SETTINGS = "TargetConfigNames:Basic";

}
