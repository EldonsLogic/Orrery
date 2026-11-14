# Development Engine Image for Orrery (ERP-001)
# Extends official Frappe ERPNext v15 with pinned Frappe HRMS and change_engine

FROM frappe/erpnext@sha256:6e016c0fc3aec5b32c14ff7c2ac97523cc864748c83ce75197779b8fe5a665a8

USER frappe

# Pinned upstream version targets
ARG HRMS_COMMIT=186900a6e3db4e6f927f1ee20df745bbb082638a

# Ensure bench virtual environment is primary in PATH
ENV PATH="/home/frappe/frappe-bench/env/bin:${PATH}"

# Clone pinned Frappe HRMS and install into bench virtualenv in editable mode
RUN if [ "${HRMS_COMMIT}" != "186900a6e3db4e6f927f1ee20df745bbb082638a" ]; then \
      echo "HRMS commit mismatch" >&2; exit 1; \
    fi && \
    git clone --depth 1 --branch v15.64.8 https://github.com/frappe/hrms.git /home/frappe/frappe-bench/apps/hrms && \
    actual_commit="$(git -C /home/frappe/frappe-bench/apps/hrms rev-parse HEAD)" && \
    if [ "${actual_commit}" != "${HRMS_COMMIT}" ]; then \
      echo "HRMS commit mismatch" >&2; exit 1; \
    fi && \
    pip install --no-cache-dir -e /home/frappe/frappe-bench/apps/hrms

# Compile the HRMS Arabic catalogue next to the base image's compiled catalogues
# (assets/locale), reached through the sites/assets link the entrypoint creates.
RUN cd /home/frappe/frappe-bench && \
    ln -sfn /home/frappe/frappe-bench/assets sites/assets && \
    bench compile-po-to-mo --app hrms --locale ar && \
    test -s assets/locale/ar/LC_MESSAGES/hrms.mo

# Copy entrypoint script
COPY --chown=1000:0 entrypoint.sh /home/frappe/entrypoint.sh
RUN chmod +x /home/frappe/entrypoint.sh

WORKDIR /home/frappe/frappe-bench

ENTRYPOINT ["/home/frappe/entrypoint.sh"]
CMD ["start"]
