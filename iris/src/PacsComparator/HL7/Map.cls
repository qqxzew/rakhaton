/// HL7 v2 to FHIR R4 mapping of the simulated RIS feed (T086).
/// ORM^O01 becomes a ServiceRequest (planned exam), ORU^R01 a DiagnosticReport (report text in conclusion).
/// Both carry the simulation tag (hard rule 5). Mirrored in backend/app/exchange/hl7.py (used by the tests).
///
/// Field use (synthetic RIS profile):
///   PID-3.1 patient id (pseudonym) | ORC-1 order control (NW new, CA cancel) | ORC-2/OBR-2 placer order number
///   ORC-3/OBR-3 filler order number | OBR-4 service id (code^Czech text) | OBR-24 modality (DICOM code)
///   OBR-15.4 body regions, ";" separated vocabulary codes | OBR-27.4 or ORC-7.4 planned date | OBR-7 observation date
///   OBR-25 result status | OBX-5 report text (TX/FT/ST, one line per OBX)
Class PacsComparator.HL7.Map Extends %RegisteredObject
{

Parameter SIMSYSTEM = "urn:pacs-comparator:simulation";

Parameter SRCSYSTEM = "urn:pacs-comparator:hl7-source";

Parameter PLACERSYSTEM = "urn:pacs-comparator:ris-placer-order";

Parameter FILLERSYSTEM = "urn:pacs-comparator:ris-filler-order";

Parameter DCM = "http://dicom.nema.org/resources/ontology/DCM";

/// "ORM^O01" style message type of the message, "" when unreadable.
ClassMethod MessageType(msg As EnsLib.HL7.Message) As %String
{
	Set seg = msg.GetSegmentAt(1)
	If '$IsObject(seg) || (seg.Name '= "MSH") Quit ""
	Quit seg.GetValueAt("9.1") _ "^" _ seg.GetValueAt("9.2")
}

ClassMethod Segment(msg As EnsLib.HL7.Message, name As %String, nth As %Integer = 1) As EnsLib.HL7.Segment
{
	Set n = 0, found = ""
	For i = 1:1:msg.SegCount {
		Set seg = msg.GetSegmentAt(i)
		If $IsObject(seg), seg.Name = name {
			Set n = n + 1
			If n = nth {
				Set found = seg
				Quit
			}
		}
	}
	Quit found
}

ClassMethod Field(seg As EnsLib.HL7.Segment, path As %String) As %String
{
	If '$IsObject(seg) Quit ""
	Quit ..Unescape($ZStrip(seg.GetValueAt(path), "<>W"))
}

/// HL7 escape sequences \.br\ \F\ \S\ \T\ \R\ \E\ to text.
ClassMethod Unescape(s As %String) As %String
{
	If s '[ "\" Quit s
	Set out = "", i = 1
	While i <= $Length(s) {
		Set c = $Extract(s, i)
		If c '= "\" {
			Set out = out _ c, i = i + 1
			Continue
		}
		Set j = $Find(s, "\", i + 1)
		If 'j {
			Set out = out _ c, i = i + 1
			Continue
		}
		Set code = $Extract(s, i + 1, j - 2)
		Set out = out _ $Case(code, "F": "|", "S": "^", "T": "&", "R": "~", "E": "\", ".br": $Char(10), : "")
		Set i = j
	}
	Quit out
}

/// HL7 date (YYYYMMDD...) to FHIR date; "" when not a date.
ClassMethod Date(ts As %String) As %String
{
	Set ts = $Extract(ts, 1, 8)
	If ts'?8N Quit ""
	Quit $Extract(ts, 1, 4) _ "-" _ $Extract(ts, 5, 6) _ "-" _ $Extract(ts, 7, 8)
}

ClassMethod ModalityText(code As %String) As %String
{
	Quit $Case(code, "PT": "PET", "CR": "RTG", "DX": "RTG", "US": "SONO", "MG": "MAMO", "NM": "SCINT", : code)
}

/// Resource id: prefix plus the order number reduced to letters, digits, "-" and "." (max 60).
ClassMethod SafeId(prefix As %String, value As %String) As %String
{
	Set out = ""
	For i = 1:1:$Length(value) {
		Set c = $Extract(value, i)
		Set out = out _ $Select(c?1(1A,1N,1"-",1"."): c, 1: "-")
	}
	Quit prefix _ $Extract(out, 1, 60)
}

ClassMethod Meta(sourceType As %String) As %DynamicObject
{
	Quit {"tag": [{"system": (..#SIMSYSTEM), "code": "simulated", "display": "Simulace"}, {"system": (..#SRCSYSTEM), "code": (sourceType), "display": "HL7 v2 ze simulovaného RIS"}]}
}

/// FHIR ServiceRequest JSON from an ORM^O01; "" when patient or placer order number is missing.
ClassMethod ServiceRequest(msg As EnsLib.HL7.Message, Output patientId As %String, Output resourceId As %String) As %String
{
	Set patientId = "", resourceId = ""
	Set msh = ..Segment(msg, "MSH"), pid = ..Segment(msg, "PID"), orc = ..Segment(msg, "ORC"), obr = ..Segment(msg, "OBR")
	Set patientId = ..Field(pid, "3.1")
	Set placer = ..Field(orc, "2.1")
	If placer = "" Set placer = ..Field(obr, "2.1")
	If patientId = "" || (placer = "") Quit ""
	Set resourceId = ..SafeId("RIS-", placer)
	Set modality = ..Field(obr, "24")
	If modality = "" Set modality = ..Field(obr, "4.1")
	Set ctl = ..Field(orc, "1")
	Set sr = {"resourceType": "ServiceRequest", "id": (resourceId)}
	Set sr.meta = ..Meta("ORM^O01")
	Set sr.identifier = [{"system": (..#PLACERSYSTEM), "value": (placer)}]
	Set sr.status = $Case(ctl, "CA": "revoked", "DC": "revoked", : "active")
	Set sr.intent = "order"
	Set sr.category = [{"coding": [{"system": "http://snomed.info/sct", "code": "363679005", "display": "Imaging"}]}]
	Set sr.code = {"coding": [{"system": (..#DCM), "code": (modality)}], "text": (..ModalityText(modality))}
	Set regions = ..Field(obr, "15.4")
	If regions '= "" {
		Set sr.bodySite = []
		For i = 1:1:$Length(regions, ";") {
			Set r = $ZStrip($Piece(regions, ";", i), "<>W")
			If r '= "" Do sr.bodySite.%Push({"text": (r)})
		}
	}
	Set sr.subject = {"reference": ("Patient/" _ patientId)}
	Set when = ..Date(..Field(obr, "27.4"))
	If when = "" Set when = ..Date(..Field(orc, "7.4"))
	If when '= "" Set sr.occurrenceDateTime = when
	Set authored = ..Date(..Field(msh, "7"))
	If authored '= "" Set sr.authoredOn = authored
	Set sr.requester = {"display": (..Field(msh, "4") _ " (simulovaný RIS)")}
	Set text = ..Field(obr, "4.2")
	If text '= "" Set sr.note = [{"text": ("Služba: " _ text _ " (HL7 v2 ORM^O01, simulace)")}]
	Quit sr.%ToJSON()
}

/// FHIR DiagnosticReport JSON from an ORU^R01; "" when patient or filler order number is missing.
ClassMethod DiagnosticReport(msg As EnsLib.HL7.Message, Output patientId As %String, Output resourceId As %String) As %String
{
	Set patientId = "", resourceId = ""
	Set msh = ..Segment(msg, "MSH"), pid = ..Segment(msg, "PID"), obr = ..Segment(msg, "OBR")
	Set patientId = ..Field(pid, "3.1")
	Set filler = ..Field(obr, "3.1"), placer = ..Field(obr, "2.1")
	If patientId = "" || (filler = "") Quit ""
	Set resourceId = ..SafeId("RIS-", filler)
	Set modality = ..Field(obr, "24")
	If modality = "" Set modality = ..Field(obr, "4.1")
	Set lines = "", n = 0
	For i = 1:1:msg.SegCount {
		Set seg = msg.GetSegmentAt(i)
		If '$IsObject(seg) || (seg.Name '= "OBX") Continue
		If '$ListFind($ListBuild("TX", "FT", "ST"), ..Field(seg, "2")) Continue
		Set lines = lines _ $Select(n: $Char(10), 1: "") _ ..Field(seg, "5"), n = n + 1
	}
	Set text = ..Field(obr, "4.2")
	If text = "" Set text = ..ModalityText(modality)
	Set dr = {"resourceType": "DiagnosticReport", "id": (resourceId)}
	Set dr.meta = ..Meta("ORU^R01")
	Set dr.identifier = [{"system": (..#FILLERSYSTEM), "value": (filler)}]
	If placer '= "" Set dr.basedOn = [{"identifier": {"system": (..#PLACERSYSTEM), "value": (placer)}}]
	Set dr.status = $Case(..Field(obr, "25"), "P": "preliminary", "C": "corrected", "A": "amended", : "final")
	Set dr.category = [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0074", "code": "RAD"}]}]
	Set dr.code = {"coding": [{"system": (..#DCM), "code": (modality)}], "text": (text)}
	Set dr.subject = {"reference": ("Patient/" _ patientId)}
	Set when = ..Date(..Field(obr, "7"))
	If when = "" Set when = ..Date(..Field(msh, "7"))
	If when '= "" Set dr.effectiveDateTime = when
	Set dr.conclusion = lines
	Quit dr.%ToJSON()
}

}
