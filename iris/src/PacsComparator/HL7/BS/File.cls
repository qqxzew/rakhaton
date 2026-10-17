Include Ensemble

/// File fallback for the simulated RIS: every *.hl7 file in FilePath (inside the IRIS container) is one
/// HL7 v2 message batch, read and archived by the file adapter.
Class PacsComparator.HL7.BS.File Extends EnsLib.HL7.Service.FileService
{

Method OnInit() As %Status
{
	// the file adapter needs its folders to exist
	For d = ..Adapter.FilePath, ..Adapter.ArchivePath, ..Adapter.WorkPath {
		If d '= "" Do ##class(%File).CreateDirectoryChain(d)
	}
	Quit ##super()
}

}
