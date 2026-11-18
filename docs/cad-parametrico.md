# CAD paramétrico da estrutura

`acdt cad <missão.yaml> -o pasta` dimensiona o avião e escreve `cad/cad_spec.json`, `cad/structure.dxf` e, quando o extra está instalado, `cad/structure.step`.

O DXF está em milímetros. A planta mostra a asa, as duas longarinas e o rectângulo da fuselagem. A secção do caixão na raiz fica ao lado. As empenagens entram na montagem STEP. Não é um desenho cotado de produção.

O STEP é uma montagem: revestimentos e longarinas do caixão, nervuras, cavernas e quatro longarinas da fuselagem. O perfil entre as longarinas é a espessura NACA de 4 dígitos (Abbott e von Doenhoff, Eq. 6.2). A espessura do revestimento é a do `WingBoxLayout`; a alma usa o mínimo do material. Não é a espessura que a encurvadura dimensionou.

A casca exterior não é redesenhada aqui. Se existir um STEP do OpenVSP, passa-se com `--oml` e entra na montagem com o nome `oml_openvsp`. Neste PC o OpenVSP não está instalado (`openvsp.org` fecha o handshake TLS), por isso a montagem de rotina é só a estrutura.

O CadQuery (Apache-2.0) importa o OpenCASCADE, que é LGPL. Esse import fica no processo de `cad_build.py`. O processo do acdt não o carrega. Instalação: `pip install "acdt[cad]"`.
