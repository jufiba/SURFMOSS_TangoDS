// Define stepper motor connections and steps per revolution:
#define dirPin 31
#define stepPin 33
#define stepsPerRevolution 200

void setup() {
  // Declare pins as output:
  pinMode(stepPin, OUTPUT);
  pinMode(dirPin, OUTPUT);

  // Iniciamos la comunicación serie a 9600 baudios
  Serial.begin(9600);
  
  Serial.println("Listo. Envia formato: +5 o -3 (Signo + número de vueltas)");
}


void loop() {

// Comprobamos si hay datos disponibles en el puerto serie
  if (Serial.available() > 0) {
    // Leemos toda la cadena hasta que encuentre un salto de línea ('\n')
    String input = Serial.readStringUntil('\n');
    input.trim(); // Eliminamos espacios o retornos de carro sobrantes

    if (input.length() > 0) {
      // El primer carácter es la dirección ('+' o '-')
      char direccion = input.charAt(0);
      
      // El resto de la cadena corresponde al número de vueltas
      String strVueltas = input.substring(1);
      int vueltas = strVueltas.toInt(); // Convertimos a número entero

      // Verificamos que el carácter de dirección sea válido
      if (direccion == '+' || direccion == '-') {
        // Calculamos los pasos totales necesarios
        long pasosTotales = (long)vueltas * stepsPerRevolution;

        Serial.print("Direccion: ");
        Serial.print(direccion);
        Serial.print(" | Vueltas: ");
        Serial.println(vueltas);

        // Si la dirección es '-', invertimos el sentido multiplicando los pasos por -1
        if (direccion == '-') {
          digitalWrite(dirPin, HIGH);
        }
         if (direccion == '+'){ 
          digitalWrite(dirPin, LOW);
        }
  // Spin the stepper motor 5 revolutions fast:
  for (int i = 0; i < pasosTotales; i++) {
    // These four lines result in 1 step:
    digitalWrite(stepPin, HIGH);
    delayMicroseconds(1200);
    digitalWrite(stepPin, LOW);
    delayMicroseconds(1200);
  }

  delay(1000);
 }
}
  }  }
