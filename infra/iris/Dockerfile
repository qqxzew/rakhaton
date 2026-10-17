# InterSystems IRIS for Health (community) with the FHIR R4 server added by backend/scripts/iris_setup.py.
# Based on the InterSystems FHIR-AI-Hackathon-Kit (docker-iris-fhir).
FROM intersystems/irishealth-community:latest-cd

ENV IRISINSTALLDIR=/usr/irissys
ENV PATH="${PATH}:${IRISINSTALLDIR}/bin"
ENV PYTHONPATH="${IRISINSTALLDIR}/lib/python"
ENV IRISNAMESPACE=USER
ENV IRISUSERNAME=SuperUser
ENV IRISPASSWORD=SYS

USER root
RUN mkdir -p /durable /home/irisowner/dev && \
    chown -R irisowner:irisowner /durable /home/irisowner/dev
WORKDIR /home/irisowner/dev
COPY merge.cpf .

USER irisowner
RUN iris start IRIS && \
    iris merge IRIS merge.cpf && \
    echo 'do ##class(Security.Users).UnExpireUserPasswords("*")' | iris session IRIS -U %SYS && \
    iris stop IRIS quietly
