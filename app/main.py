#!/usr/bin/env python3
import platform
import uuid
import sys
import os.path
import shlex
import asyncio
import yaml

from nicegui import ui # type: ignore

def getChildElements(parent=None) -> list:
    if parent is None:
        return []
    return parent.default_slot.children

@ui.page('/')
async def main():

    container_clusters = None

    def_card_width = "95%"

    secretHeaders ={
        TYPE_GENERIC: ['Secret-Key', 'Secret-Value'],
    }

    secretData = {
        TYPE_GENERIC: [
            {"key": "user", "value": "secret!"}
        ],
        TYPE_DOCKER: [
            {"label": 'Registry',    "key": "url",       "value": "https://quay.io"},
            {"label": 'Email',       "key": "email",     "value": "user@example.com"},
            {"label": 'User',        "key": "username",  "value": "user"},
            {"label": 'Password',    "key": "password",  "value": "password"},
        ],
        TYPE_TLS: [
            {"label": 'Certificate',    "key": "cert", "value": ""},
            {"label": 'Private Key',    "key": "key",  "value": ""},
        ],
    }

    def clearAll():
        for clusterName in clusterConfig['clusters'].keys():
            widgets = output_containers[clusterName]
            widgets["INPUT1"].set_value("# press Encrypt button!")
            widgets["HIDDEN_INPUT1"].set_text("")
            widgets["INPUT2"].set_value("")
            widgets["HIDDEN_INPUT2"].set_text("")
        ui.notify(f"Cleared all clusters!")


    async def encryptAll() -> None:
        if scope.value == 'strict' and not secretName.value:
            ui.notify("Secret Name is required for STRICT scope!", type="negative")
            return
        
        # simple validation
        if secret_type.value == TYPE_GENERIC:
            for idx, obj in enumerate(secretData[TYPE_GENERIC]):
                if not obj['key'].strip():
                    ui.notify(f"Key is required for secret {idx+1}!", type="negative")
                    return
                if not obj['value'].strip():
                    ui.notify(f"Value is required for secret {idx+1}!", type="negative")
                    return
                
        elif secret_type.value == TYPE_DOCKER:
            for idx, obj in enumerate(secretData[TYPE_DOCKER]):
                if not obj['value'].strip():
                    ui.notify(f"{obj['label']} is required!", type="negative")
                    return
                    
        if not namespace.value and scope.value != SCOPE_CLUSTER_WIDE:
            ui.notify("Namespace is required!", type="negative")
            return

        if not secretName.value:
            # secretName.set_value("my-secret")
            secretName.set_value("my-secret")
            ui.notify(f"Secret Name set to '{secretName.value}'", type="warning") 
            
        for cluster in getChildElements(container_clusters):
            if cluster.value:
                ui.notify(f"Encrypting for {cluster.text}")
                await encryptForCluster(cluster.text)


    async def encryptForCluster(clusterName: str) -> None:
        ns = namespace.value
        if prefix.value and clusterConfig['clusters'][clusterName].get('namespacePrefix', False):
            ns = clusterConfig['clusters'][clusterName]['namespacePrefix'] + namespace.value

        widgets = output_containers[clusterName ]

        for secret in secretData[secret_type.value]:
            await encryptSecret(clusterName, ns, secret)
            widgets["INPUT1"].set_value("")
            widgets["HIDDEN_INPUT1"].set_text("")

        # all secrets are now encrypted for this cluster!
        s1 = ""; s2 = ""; allSecrets = ""
        for secret in secretData[secret_type.value]:
            secretKey = secret['key'].strip()
            secretVal = secret['value'].strip()
            encryptedString = secret['encrypted']
            ks_command = secret['cmd']
            # append all encrypted strings to the output widget1 (and hidden widget2 for copying!
            s1 = s1 + f"\n\n# cmd: echo -n 'xxx' | {ks_command} \n# secret-key='{secretKey}'\n{encryptedString}"
            if len(secretData[secret_type.value]) > 1:
                s2 = s2 + f"\n# secret-key='{secretKey}'" # add comment before each secret if more than one secret displayed!
            s2 = s2 + f"\n{encryptedString}"
            allSecrets = allSecrets + f"    {secretKey}: {encryptedString}\n"


        widgets["INPUT1"].set_value(s1.lstrip()) 
        widgets["HIDDEN_INPUT1"].set_text(s2.lstrip()) # set into hidden label for copying
        
        # also put into manifest widget
        if scope.value == SCOPE_CLUSTER_WIDE:
            manifest_namespace = f"namespace: null"
        else:
            manifest_namespace = f"namespace: {ns}"

        manifest = generic_secret_template.format(SCOPE=scope.value, SECRETNAME=secretName.value, NAMESPACE=manifest_namespace, ENCRYPTEDSECRETS=(allSecrets.rstrip()))
        widgets["INPUT2"].set_value(manifest)
        widgets["HIDDEN_INPUT2"].set_text(manifest) # set into hidden label for copying



    async def encryptSecret(clusterName: str, ns: str, secret: dict) -> None:
        read, write = os.pipe()

        secretKey = secret['key'].strip()
        secretVal = secret['value'].strip()

        if scope.value == SCOPE_STRICT:
            ks_param_name = f"--name {secretName.value}"
        else:
            ks_param_name = ""
        
        if scope.value == SCOPE_CLUSTER_WIDE:
            ks_param_namespace = ""
        else:
            ks_param_namespace = f"--namespace '{ns}'"

        command1 = f"echo -n '{secretVal}'"
        process1 = await asyncio.create_subprocess_exec(
            *shlex.split(command1, posix='win' not in sys.platform.lower()),
            stdout=write, 
            stderr=asyncio.subprocess.STDOUT,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        os.close(write)

        ks_command = f"kubeseal --cert {clusterConfig['clusters'][clusterName]['url']} --scope '{scope.value}' {ks_param_namespace} {ks_param_name} --raw --from-file=/dev/stdin"
        process2 = await asyncio.create_subprocess_exec(
            *shlex.split(ks_command, posix='win' not in sys.platform.lower()),
            stdin=read,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        os.close(read)

        # NOTE we need to read the output in chunks, otherwise the process2 will block
        output = '' 
        while True:
            new = await process2.stdout.read(4096)
            if not new:
                break
            output += new.decode()
        
        # store in secretData dictionary
        secret['encrypted'] = output
        secret['cmd'] = ks_command



    # callback for the prefix checkbox, to auto-update the namespace field in the encrypted secrets labels!
    def refresh_namespace() -> None:
        x = namespace.value
        namespace.set_value("")
        namespace.set_value(x)


    def callb_update_label(namespace: str, clusterName: str) -> str:
        # ui.notify(f"Prefix is {prefix.value}")  
        if not namespace:
            ns = "n/a"
        elif prefix.value and clusterConfig['clusters'][clusterName].get('namespacePrefix', False):
            ns = clusterConfig['clusters'][clusterName]['namespacePrefix'] + namespace
        else:
            ns = namespace
        return f"Encrypted secret for cluster \"{clusterName}\" and namespace \"{ns}\""


    def addSecret(index=0):
        if secret_type.value != TYPE_GENERIC:
            return
        if len(secretData[TYPE_GENERIC]) >= MAX_SECRETS:
            ui.notify(f"won't add more than {MAX_SECRETS} secrets!", type="warning")
            return
        secretData[TYPE_GENERIC].insert(index + 1, {"key": f"user-{uuid.uuid4().hex[:4]}", "value": "secret"})
        # ui.notify(f"add index from: {index}")
        populateSecretGrid(secretsGrid)

    def removeSecret(index=0):
        if secret_type.value != TYPE_GENERIC:
            return
        if len(secretData[TYPE_GENERIC]) > 1:
            del secretData[TYPE_GENERIC][index]
            # ui.notify(f"remove index: {index}")
            populateSecretGrid(secretsGrid)
        else:
            ui.notify(f"won't remove last secret!", type="warning")

    def populateSecretGrid(aGrid: ui.grid):
        if secret_type.value == TYPE_GENERIC:
            populateSecretGrid_Generic(aGrid)
        elif secret_type.value == TYPE_DOCKER:
            populateSecretGrid_Docker(aGrid)
        elif secret_type.value == TYPE_TLS:
            populateSecretGrid_TLS(aGrid)
        else:
            ui.notify(f"Unknown secret type: {secret_type.value}", type="warning")

    def populateSecretGrid_TLS(aGrid: ui.grid):
        aGrid.clear()
        aGrid.style("grid-template-columns: auto auto auto 3fr")
        with aGrid:
            for idx, obj in enumerate(secretData[TYPE_TLS]):
                ui.label(obj['label']).classes('col-span-3 p-1 font-bold')
                i = ui.textarea(label=obj['key'],value=obj['value'], placeholder="", validation={'Input too long': lambda value: len(value) < 8000, 'Required': lambda value: len(value) > 0})
                i.classes('p-1 pl-4').props('outlined').style("font-family: monospace;") 
                i.bind_value_to(obj, 'value')

    def populateSecretGrid_Docker(aGrid: ui.grid):
        aGrid.clear()
        aGrid.style("grid-template-columns: auto auto auto 3fr")
        with aGrid:
            for idx, obj in enumerate(secretData[TYPE_DOCKER]):
                ui.label(obj['label']).classes('col-span-3 p-1 font-bold')
                i = ui.input(label=obj['key'],value=obj['value'], placeholder="", validation={'Input too long': lambda value: len(value) < 1024, 'Required': lambda value: len(value) > 0})
                i.classes('p-1 pl-4').props('outlined').style("font-family: monospace;") 
                # i.style("font-family: monospace;")
                i.bind_value_to(obj, 'value')


    def populateSecretGrid_Generic(aGrid: ui.grid):
        aGrid.clear()
        aGrid.style("grid-template-columns: auto auto 2fr 3fr")
        with aGrid:
            ui.label('').classes('col-span-2')    # first 2 grid cells need to be invisible/empty (+/- icons column!)
            for h in secretHeaders[TYPE_GENERIC]:
                ui.label(h).classes('font-bold pl-1')    # first 2 labels will be invisible/empty for the icons!
            for idx, obj in enumerate(secretData[TYPE_GENERIC]):
                ui.icon('add_box', color='green').classes('text-2xl pr-2 opacity-40 hover:opacity-90').on('click', lambda idx=idx: addSecret(idx))
                ui.icon('remove_circle_outline', color='red').classes('text-2xl pr-3 opacity-40 hover:opacity-90').on('click', lambda idx=idx: removeSecret(idx))
                
                inputKey = ui.input(label='key',value=obj['key'], placeholder="e.g. user", validation={'Input too long': lambda value: len(value) < 1024, 'Required': lambda value: len(value) > 0})
                inputKey.props('outlined').classes('p-1').style("font-family: monospace;")
                inputKey.bind_value_to(secretData[TYPE_GENERIC][idx], 'key')
                
                inputVal = ui.textarea(label='value',value=obj['value'], placeholder="e.g. top-secret!", validation={'Input too long': lambda value: len(value) < 8000, 'Required': lambda value: len(value) > 0})
                inputVal.props('outlined autogrow input-class=max-h-56').classes('p-1').style("font-family: monospace;")
                inputVal.bind_value_to(secretData[TYPE_GENERIC][idx], 'value')


    #########################################################################
    # CARD#1 : CLUSTER SELECTION
    #########################################################################
    with ui.card().style(f'width: {def_card_width}'):
        
        with ui.row().classes('w-full justify-end'):
            dark = ui.dark_mode()
            dark.auto()
            with ui.button_group().props('push glossy').classes('absolute top-4 '):
                ui.button('Dark', on_click=dark.enable, color='grey').props('push').style('font-size: 0.8em')
                ui.button('Light', on_click=dark.disable, color='white').props('push text-color=black').style('font-size: 0.8em')
                # ui.button('Auto', on_click=dark.auto, color='white').props('push text-color=black').style('font-size: 0.8em')

        
        # CLUSTER SELECTION
        with ui.row().classes('items-center gap-4'):
            ui.label(f"CLUSTERS").classes('font-bold text-sky-500')
            ui.icon('done_all', size='xs').classes('opacity-50 hover:opacity-90 p-0').on("click", lambda: [x.set_value(True) for x in getChildElements(container_clusters)])
            ui.icon('check_box_outline_blank', size='xs').classes('opacity-50 hover:opacity-90 p-0').on("click", lambda: [x.set_value(False) for x in getChildElements(container_clusters)])
            # build the cluster selection checkboxes
            with ui.row() as container_clusters:
                for clusterName, configObj in clusterConfig['clusters'].items():
                    with ui.checkbox(clusterName) as checkbox:
                        checkbox.set_value(True if configObj['enabled'] == True else False)
                        ui.tooltip(f"URL: {configObj['url']}\nNAMESPACE PREFIX: {configObj.get('namespacePrefix','n/a')}" ).classes('bg-sky-600 text-white text-sm').style('white-space: pre-wrap')


        # sealing options
        with ui.row().classes('items-center'):    
            ui.label(f"SEALING SCOPE").classes('font-bold text-sky-500')
            tt_text = 'STRICT: You must not change sealed-secret name after encryption!\nNAMESPACE-WIDE: ok to rename sealed-secret later inside *same* namespace.\nCLUSTER-WIDE: will decrypt in any namespace. - ☝ Use in exceptional cases only! ☝'
            with ui.toggle(SCOPES, value=SCOPES[DEF_SCOPE_IDX]).props('glossy no-caps').classes('ml-4') as scope:
                ui.tooltip(tt_text).classes('bg-sky-600 text-white text-sm').style('white-space: pre-wrap')



    #########################################################################
    # CARD#2 : SECRET INPUT fields
    #########################################################################

    with ui.card().style(f'width: {def_card_width}'):
        # SECRET NAMESPACE Field
        with ui.row().classes('items-center'):
            ui.label("Secret NAMESPACE").classes("text-sky-600 font-bold w-24")
            namespace = ui.input(label='Namespace of the Kubernetes Secret', 
                        placeholder='e.g. demo', value="demo",
                        validation={'Input too long: > 64 chars!': lambda value: len(value) < 64, 'Required': lambda value: len(value) > 0 or scope.value == SCOPE_CLUSTER_WIDE})
            namespace.props('size=80 outlined')
            
            # add PREFIX checkbox
            prefix = ui.checkbox("Use cluster-specific namespace prefix")
            prefix.on_value_change(lambda: refresh_namespace())
            prefix.set_value(False)
            with prefix:
                ui.tooltip('E.g. `dev-demo` on `dev` cluster.\nPrefixes can be defined in config.yaml.').classes('bg-sky-600 text-white text-sm').style('white-space: pre-wrap')
            

        # SECRET NAME Field
        with ui.row().classes('items-center'):
            ui.label("Secret NAME").classes("text-sky-600 font-bold w-24")
            secretName = ui.input(label='Name of Kubernetes Secret (can be changed later except when using the STRICT sealing scope!)', 
                        placeholder='e.g. db-credentials', value="my-secret",
                        validation={'Input too long: > 64 chars!': lambda value: len(value) < 64, 'Required for generating the manifest!': lambda value: len(value) > 0})
            secretName.props('size=80 outlined')

        # SECRET TYPE Field
        with ui.row().classes('items-center'):    
            ui.label(f"Secret TYPE").classes("text-sky-600 font-bold w-24")
            tt_text = 'todo'
            with ui.toggle(S_TYPES, value=DEFAULT_SECRET_TYPE).props('glossy no-caps').classes() as secret_type:
                ui.tooltip(tt_text).classes('bg-sky-600 text-white text-sm').style('white-space: pre-wrap')
            secret_type.on_value_change(lambda: populateSecretGrid(secretsGrid))

        # SECRET KEY and VALUE fields
        # secretsGrid = ui.grid(columns='30px 36px 1fr 2fr').classes('items-start w-5/6 gap-0 p-4 text-sky-600')
        secretsGrid = ui.grid().classes('items-center w-4/6 gap-0 p-4 text-sky-600')
        secretsGrid.style("grid-template-columns: auto auto auto 3fr")
    
        populateSecretGrid(secretsGrid)

        with ui.row().classes('items-center'):
            ui.button("ENCRYPT !", color="green").props("glossy").classes("w-32").on_click(encryptAll)
            ui.button("clear", color="grey").props("glossy").classes("w-32").on_click(clearAll)



    #########################################################################
    # CARD #3 : OUTPUT CONTAINERS
    #########################################################################

    # 1 OUTPUT CARD PER CLUSTER
    # keep track of cluster containers in this dict: output_containers
    output_containers = {} 

    with ui.column().classes("gap-16 w-full").style(f'width: {def_card_width}'):
        for cluster_chkbox in getChildElements(container_clusters):
            clName = cluster_chkbox.text

            with ui.card().classes("w-full") as card:
                card.bind_visibility_from(cluster_chkbox, "value")
                
                cluster_widgets = {}
                output_containers[clName] = cluster_widgets
                
                container = ui.column().classes('items-left w-full').bind_visibility_from(cluster_chkbox, "value")
                cluster_widgets["CONTAINER"] = container
                
                with container:
                    # LABEL FOR ENCRYPTED SECRET
                    l = ui.label(f"Encrypted string for cluster: \"{clName}\" and namespace \"{'PREFIX ' + namespace.value if prefix.value else namespace.value}\"")
                    l.classes('font-bold text-lg dark:text-sky-500')
                    l.bind_text_from(namespace, "value", backward=lambda ns=namespace.value, clName=clName: callb_update_label(ns, clName)) # creates a closure for the callback!
                    
                    # SEALED-SECRET OUTPUT TEXT FIELD 
                    # Visible SEALED-SECRET OUTPUT TEXT FIELD (YAML CODE MIRROR)
                    code = ui.codemirror(value="# press Encrypt button!", language="YAML", theme="quietlight", line_wrapping=True).classes("w-full h-48")
                    code.props("readonly")
                    # hidden label to simply store the secret-text FOR COPYING (ugly hack)
                    copycode = ui.label().classes('hidden')
                    copyIcon = ui.icon('content_copy', size='xs').on('click', js_handler=f'() => navigator.clipboard.writeText(getElement("{copycode.id}").innerText)')
                    copyIcon.classes('absolute right-4 top-10 opacity-40 hover:opacity-80 cursor-pointer').tooltip('Copies the raw encrypted string(s) to clipboard')

                    # store references for lates use to access the widgets
                    cluster_widgets["INPUT1"] = code
                    cluster_widgets["HIDDEN_INPUT1"] = copycode

                    # show another code field for the MANIFEST
                    ui.label(f"Complete Sealed-Secret Manifest").classes("font-semibold text-base dark:text-sky-500")
                    code2 = ui.codemirror(value=f"", language="YAML", theme="quietlight", line_wrapping=False).classes("w-full h-64")

                    # hidden label to simply store the manifest FOR COPYING (ugly hack)
                    copycode2 = ui.label().classes('hidden')
                    copyIcon2 = ui.icon('content_copy', size='xs').on('click', js_handler=f'() => navigator.clipboard.writeText(getElement("{copycode2.id}").innerText)')
                    copyIcon2.classes('absolute right-4 top-72 opacity-40 hover:opacity-80 cursor-pointer').tooltip('Copies the complete manifest to clipboard')

                    # store references for lates use to access the widgets
                    cluster_widgets["INPUT2"] = code2
                    cluster_widgets["HIDDEN_INPUT2"] = copycode2

                    # ui.select(code.supported_themes, label='Theme').classes('w-32').bind_value(code, 'theme')
                    # ui.select(code2.supported_themes, label='Theme').classes('w-32').bind_value(code2, 'theme')

    # Help text
    ui.label("Please select the cluster(s) you want to encrypt the secret for and click the 'ENCRYPT' button. The sealed secret will be displayed above.").style('color: grey; font-weight: normal')


# MAIN

MAX_SECRETS = 10

clusterConfig = {   # default config
  'defaults': {
    'enable-cluster-wide-encryption': 'true',
    'max-secrets': 7,
  },
  'clusters': {
    'demo-cluster': {
        'url': "http://cert.sealedsecrets.dev.example.com/v1/cert.pem",
        'namespacePrefix': "dev-",
        'enabled': 'true',
    }    
  }
}

generic_secret_template = """
apiVersion: bitnami.com/v1alpha1
kind: SealedSecret
metadata:
  name: {SECRETNAME}
  {NAMESPACE}
  annotations:
    sealedsecrets.bitnami.com/{SCOPE}: "true"
spec:
  encryptedData:
{ENCRYPTEDSECRETS}
  template:
    metadata:
      name: {SECRETNAME}
      {NAMESPACE} 
      annotations:
        sealedsecrets.bitnami.com/{SCOPE}: "true"
""".strip()


configName = "/config/config.yaml"
config = os.getenv("CONFIG")
if config:
    configName = config

# try to load config from file
if os.path.isfile(configName):
    with open(configName, 'r') as file:
        clusterConfig = yaml.safe_load(file)
else:
    print(f"\nWARN: Config file '{configName}' not found! Using default config for demo purposes only.\n")


SCOPE_STRICT = 'strict'
SCOPE_NS_WIDE = 'namespace-wide'
SCOPE_CLUSTER_WIDE = 'cluster-wide'

SCOPES = [ SCOPE_STRICT, SCOPE_NS_WIDE ] 
DEF_SCOPE_IDX = 1

TYPE_GENERIC = "generic"
TYPE_DOCKER  = "docker-registry" 
TYPE_TLS  = "tls" 
S_TYPES = [ TYPE_GENERIC, TYPE_DOCKER, TYPE_TLS ] 
DEFAULT_SECRET_TYPE = TYPE_GENERIC


if clusterConfig['defaults'].get('enable-cluster-wide-encryption', False):
    SCOPES.append(SCOPE_CLUSTER_WIDE)

MAX_SECRETS = clusterConfig['defaults'].get('max-secrets', MAX_SECRETS)


ui.run(title="Sealed Secrets Helper", reload=platform.system() != 'Windows ', storage_secret=uuid.uuid4().hex)
