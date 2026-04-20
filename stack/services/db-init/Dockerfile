FROM postgres:17-alpine

COPY init.sh /init.sh
COPY sql/ /sql/
RUN chmod +x /init.sh

ENTRYPOINT ["/init.sh"]
