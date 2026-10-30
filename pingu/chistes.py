"""Chistes del pingüino: colección propia en español, sin depender de internet.
No repite ninguno hasta haberlos contado todos (se acuerda entre reinicios).
Cada chiste es (planteamiento, remate); el remate se muestra un momento después.
Remate "" = chiste de una sola línea."""
import random

CHISTES = [
    # --- Clásicos ---
    ("¿Qué le dice un jaguar a otro jaguar?", "Jaguar you?"),
    ("¿Cuál es el colmo de un electricista?", "Que su mujer se llame Luz y sus hijos le sigan la corriente."),
    ("¿Qué hace una abeja en el gimnasio?", "¡Zum-ba!"),
    ("¿Por qué las focas miran siempre hacia arriba?", "¡Porque ahí están los focos!"),
    ("¿Qué le dice una iguana a su hermana gemela?", "Somos iguanitas."),
    ("¿Cómo se dice pañuelo en japonés?", "Saka-moko."),
    ("¿Cuál es el café más peligroso del mundo?", "El ex-preso."),
    ("¿Qué le dice el 0 al 8?", "Bonito cinturón."),
    ("¿Qué le dice una pared a otra pared?", "Nos vemos en la esquina."),
    ("¿Cuál es el colmo de un jardinero?", "Que siempre lo dejen plantado."),
    ("¿Qué hace un pez?", "Nada."),
    ("¿Cómo se queda un mago después de comer?", "Magordito."),
    ("¿Por qué el libro de matemáticas está triste?", "Porque tiene muchos problemas."),
    ("¿Qué le dice un techo a otro techo?", "Techo de menos."),
    ("¿Cuál es el animal más antiguo?", "La cebra, porque está en blanco y negro."),
    ("¿Qué le dice un pato a otro pato?", "Estamos empatados."),
    ("¿Qué le dijo el semáforo al coche?", "No me mires, que me estoy cambiando."),
    ("¿Cómo se llama el campeón de buceo japonés?", "Tokofondo. ¿Y el subcampeón? Kasitoko."),
    ("—Camarero, ¿el pescado viene solo?", "—No, señor, se lo traigo yo."),
    ("—Doctor, doctor, tengo complejo de feo.", "—Hombre, de complejo nada."),
    ("—Doctor, veo bolitas de colores.", "—¿Ha visto ya al oculista? —No, solo bolitas de colores."),
    ("¿Cuál es el colmo de un astronauta?", "Que le dejen sin espacio."),
    ("¿Qué le dice un cable a otro cable?", "Somos los intocables."),
    ("¿Qué le dice el tomate a la cebolla?", "No te hagas la que lloras."),
    ("¿Por qué el esqueleto no fue a la fiesta?", "Porque no tenía cuerpo para ello."),
    ("Mamá, mamá, en el colegio me llaman despistado.", "Niño, vete a tu casa, que esta no es."),
    ("¿Sabes cuál es el último animal que subió al arca de Noé?", "El delfín."),
    ("¿Qué le dice una impresora a otra?", "¿Esa hoja es tuya o es impresión mía?"),

    # --- Pingüinos ---
    ("¿Por qué los pingüinos no tienen ordenador portátil?", "Porque les da miedo que se les congele la pantalla."),
    ("¿Qué le dice un pingüino a otro en una fiesta?", "¡Rompamos el hielo!"),
    ("¿Dónde guardan los pingüinos el dinero?", "En un banco de hielo."),
    ("¿Qué le dice un pingüino a su pareja el día de San Valentín?", "Te quiero un iglú."),
    ("¿Por qué los pingüinos caminan así?", "Porque con frac no se puede correr."),
    ("Soy un pingüino trabajando en una oficina con calefacción.", "Esto no es teletrabajo: es supervivencia."),

    # --- Informática ---
    ("¿Por qué los programadores confunden Halloween con Navidad?", "Porque OCT 31 == DEC 25."),
    ("Solo hay 10 tipos de personas en el mundo…", "…las que entienden binario y las que no."),
    ("¿Cuántos programadores hacen falta para cambiar una bombilla?", "Ninguno: es un problema de hardware."),
    ("¿Por qué el programador dejó su trabajo?", "Porque no le daban arrays."),
    ("Un SQL entra en un bar, se acerca a dos mesas y les pregunta:", "—¿Puedo hacer un JOIN?"),
    ("En mi máquina funciona.", "Pues mandamos tu máquina a producción."),
    ("¿Qué le dice un bit a otro bit?", "Nos vemos en el bus."),
    ("¿Por qué Java no se pone gafas?", "Porque no ve C#."),
    ("Hay dos cosas difíciles en informática: invalidar la caché, poner nombres a las cosas…", "…y los errores por uno."),
    ("Un programador va al súper. Su pareja le dice: «Compra una barra de pan y, si hay huevos, trae seis».",
     "Vuelve con seis barras de pan: «Había huevos»."),
    ("¿Por qué los programadores prefieren el modo oscuro?", "Porque la luz atrae a los bugs."),
    ("El código funciona y no sé por qué.", "El código no funciona y no sé por qué. Ser programador, resumido."),
    ("¿Qué es un terapeuta?", "1024 gigapeutas."),
    ("—Toc, toc. —¿Quién es? —…", "(muy largo silencio) —Java."),
    ("Mi contraseña es «incorrecta».", "Así cuando la olvido, el sistema me la recuerda."),
    ("He reiniciado el router.", "Ahora sí que no funciona nada, pero con más estabilidad."),
    ("git commit -m \"arreglo final\"", "git commit -m \"arreglo final de verdad\"\ngit commit -m \"ahora sí\""),

    # --- Oficina ---
    ("Esta reunión podría haber sido un correo.", "Y ese correo podría no haberse enviado."),
    ("¿Cuál es el colmo de un informático?", "Tener un hijo que no tenga memoria y una hija que no tenga disco."),
    ("Me dijeron: «Trabaja de forma más inteligente, no más dura».", "Ahora trabajo igual de duro, pero me siento más tonto."),
    ("¿Por qué el café va a terapia?", "Porque le han molido a disgustos."),
    ("Lunes por la mañana:", "Mi cuerpo ha fichado. Mi cerebro llega en la reunión de las 11."),
    ("—¿Tienes un minuto?", "Lo más largo que existe en una oficina."),
    ("¿Cuál es el deporte favorito en la oficina?", "El salto de reunión en reunión."),
    ("¿Sabes por qué los viernes son tan cortos?", "Porque el lunes se lleva todas las horas."),
]

_CLAVE = "chistes_pendientes"


def siguiente(settings: dict) -> tuple:
    """Devuelve (planteamiento, remate) sin repetir hasta agotar la colección.
    Apunta en settings los que quedan; guardarlo es cosa de quien llama."""
    pendientes = [i for i in settings.get(_CLAVE, []) if isinstance(i, int) and 0 <= i < len(CHISTES)]
    if not pendientes:
        pendientes = list(range(len(CHISTES)))
        random.shuffle(pendientes)
    i = pendientes.pop()
    settings[_CLAVE] = pendientes
    return CHISTES[i]
