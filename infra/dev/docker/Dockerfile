# Development Engine Image for Orrery (ERP-001)
# Extends official Frappe ERPNext v15 with pinned Frappe HRMS and change_engine

FROM frappe/erpnext:v15

USER frappe

# Pinned upstream version targets
ARG HRMS_TAG=v15.64.8
ARG HRMS_COMMIT=186900a6e3db4e6f927f1ee20df745bbb082638a

# Ensure bench virtual environment is primary in PATH
ENV PATH="/home/frappe/frappe-bench/env/bin:${PATH}"

# Clone pinned Frappe HRMS and install into bench virtualenv in editable mode
RUN git clone --depth 1 --branch ${HRMS_TAG} https://github.com/frappe/hrms.git /home/frappe/frappe-bench/apps/hrms && \
    pip install --no-cache-dir -e /home/frappe/frappe-bench/apps/hrms

# Copy entrypoint script
COPY --chown=1000:0 entrypoint.sh /home/frappe/entrypoint.sh
RUN chmod +x /home/frappe/entrypoint.sh

WORKDIR /home/frappe/frappe-bench

ENTRYPOINT ["/home/frappe/entrypoint.sh"]
CMD ["start"]
