from . import models

def set_domain(env):
    import os
    domain = os.getenv("DOMAIN")
    if domain:
        company_name = domain.split(".")[0]
        company_id = env.ref("base.main_company")
        company_id.write({"name": company_name,"domain": domain})

