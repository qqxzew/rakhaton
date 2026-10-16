"""Quick manual probe of the IRIS C-FIND business service (counts only, no patient data)."""

import sys

import iris

target = sys.argv[1] if len(sys.argv) > 1 else "MOTOL"
patient = sys.argv[2] if len(sys.argv) > 2 else "PAC-TEST-0001"
conn = iris.createConnection("localhost", 1972, "PACSDICOM", "SuperUser", "SYS")
print(iris.createIRIS(conn).classMethodValue("PacsDicom.Api", "CFind", target, patient, "", ""))
