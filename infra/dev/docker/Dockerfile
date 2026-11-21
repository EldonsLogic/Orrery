# Development engine image for the platform (ERP-001)
# Extends official Frappe ERPNext v15 with pinned Frappe HRMS and change_engine

FROM frappe/erpnext@sha256:6e016c0fc3aec5b32c14ff7c2ac97523cc864748c83ce75197779b8fe5a665a8 AS bench

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

# The headless runtime has no outbound network. Its declared build backend must
# already be installed so mounting the app never needs package-index access.
FROM bench AS headless
RUN pip install --no-cache-dir --no-deps \
    'https://files.pythonhosted.org/packages/f2/65/b6ba90634c984a4fcc02c7e3afe523fef500c4980fec67cc27536ee50acf/flit_core-3.12.0-py3-none-any.whl#sha256=e7a0304069ea895172e3c7bb703292e992c5d1555dd1233ab7b5621b5b69e62c'
ENV ENGINE_OFFLINE_INSTALL=1

# Preserve the existing developer image as the default build target.
FROM bench AS development
