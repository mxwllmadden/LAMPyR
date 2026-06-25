// This Firmware is intended for an Arduino UNO with the HudaHubR0.3 Shield

#include <Encoder.h>
#include <Servo.h>
#include <TaskScheduler.h>

// -----------------------------------------------------------------------------
// Pin Definitions
// -----------------------------------------------------------------------------

#define RIG_ID "BanditHudaHub_1"

#define SPEAKERPIN          6
#define REWARDPIN           9
#define MANUALREWARDPIN     13
#define LASERPIN            11
#define CAM_PIN             12

#define LICKOMETERDIGPIN    A2
#define LICKOMETERANALOGPIN A3

#define SERVOMOTORPIN       5

#define ROTARYPIN1          2
#define ROTARYPIN2          3

// -----------------------------------------------------------------------------
// Task Periods
// -----------------------------------------------------------------------------

#define LICK_PERIOD_MS      10
#define ROTARY_PERIOD_MS    20
#define CAM_PULSE_PERIOD_MS 50
#define CAM_PULSE_WIDTH_US  100

// -----------------------------------------------------------------------------
// Hardware
// -----------------------------------------------------------------------------

Scheduler runner;

Encoder rotary(ROTARYPIN1, ROTARYPIN2);
Servo wheelLock;

// -----------------------------------------------------------------------------
// State
// -----------------------------------------------------------------------------

//debugging
bool suppressLickReports = false;
bool suppressRotaryReports = false;
bool suppressCommandReports = false;
int code = 0;

// Camera Pulse
bool camPulseActive = false;
uint32_t camPulseStart = 0;
bool camOnline = false;

// Laser
bool rampingDown = false;
uint32_t rampStartUs = 0;
uint32_t rampDurationUs = 0;
int rampStartPWM = 255;
int pwm_last = -1;

// Rotary
long rotarypos = 0;
long rotarypos_last = 0;
long rotarydiff = 0;

// Lick
int currentlickanalog = 0;
int currentlickdigital = 0;

// Reward
bool rewarding = false;
uint32_t rewardStart = 0;
uint32_t rewardsize = 500;      // microseconds
uint32_t rewardError = 0;

// Manual reward button
bool manualRewardState = HIGH;
bool manualRewardLastState = HIGH;

// Lock
int angle = 0;

// Loop frequency measurement
bool measureLoopRequested = false;

uint32_t loopCounter = 0;
uint32_t loopCounterStart = 0;

bool pauseAfterReport = false;
uint32_t pauseStart = 0;


// -----------------------------------------------------------------------------
// Camera Pulses
// -----------------------------------------------------------------------------
void triggerCameraPulse()
{
    if (!camOnline)
        return;
    digitalWrite(CAM_PIN, HIGH);

    camPulseActive = true;
    camPulseStart = micros();
    reportCamPulse();
}

// -----------------------------------------------------------------------------
// Reporting
// -----------------------------------------------------------------------------

void reportCamPulse()
{
    Serial.print(millis());
    Serial.print("\tP\t");
    Serial.println(millis());
}

void reportCommand(char cmd)
{
    if (suppressCommandReports)
        return;
    Serial.print(millis());
    Serial.print("\tC\t");
    Serial.println((int)cmd);
}

void reportRotary()
{
    if (suppressRotaryReports)
        return;
    rotarypos = rotary.read();

    rotarydiff = rotarypos_last - rotarypos;

    Serial.print(millis());
    Serial.print("\tR\t");
    Serial.println(rotarydiff);

    rotarypos_last = rotarypos;
}

void reportLick()
{
    if (suppressLickReports)
        return;
    currentlickanalog = analogRead(LICKOMETERANALOGPIN);
    currentlickdigital = analogRead(LICKOMETERDIGPIN);

    Serial.print(millis());
    Serial.print("\tA\t");
    Serial.println(currentlickanalog);

    Serial.print(millis());
    Serial.print("\tL\t");
    Serial.println(currentlickdigital);
}

void reportRewardSize()
{
    Serial.print(millis());
    Serial.print("\tW\t");
    Serial.println(rewardsize);
}

void reportReward()
{
    Serial.print(millis());
    Serial.print("\tG\t");
    Serial.println(rewardsize);
}

void reportManualReward()
{
    Serial.print(millis());
    Serial.print("\tM\t");
    Serial.println(1);
}

void reportTime()
{
    Serial.print(millis());
    Serial.print("\tT\t");
    Serial.println(millis());
}

void reportRewardError()
{
    Serial.print(millis());
    Serial.print("\tE\t");
    Serial.println(rewardError);
}

void reportLoopHz(uint32_t hz)
{
    Serial.print(millis());
    Serial.print("\tF\t");
    Serial.println(hz);
}

// -----------------------------------------------------------------------------
// Reward Handling
// -----------------------------------------------------------------------------

void giveReward()
{
    if (rewarding)
        return;

    digitalWrite(REWARDPIN, HIGH);

    rewardStart = micros();
    rewarding = true;
}

void checkReward()
{
    if (!rewarding)
        return;

    uint32_t elapsed = micros() - rewardStart;

    if (elapsed >= rewardsize)
    {
        rewardError = elapsed - rewardsize;

        digitalWrite(REWARDPIN, LOW);

        rewarding = false;
    }
}

// -----------------------------------------------------------------------------
// Manual Reward Button
// -----------------------------------------------------------------------------

void checkManualReward()
{
    manualRewardState = digitalRead(MANUALREWARDPIN);

    if (manualRewardLastState == HIGH &&
        manualRewardState == LOW)
    {
        reportManualReward();

        giveReward();

        reportReward();
    }

    manualRewardLastState = manualRewardState;
}

// -----------------------------------------------------------------------------
// Commands
// -----------------------------------------------------------------------------

void executeCommand(char cmd)
{
    if (cmd == '\n' || cmd == '\r')
        return;
    reportCommand(cmd);
    switch (cmd)
    {
        case 'p':
            tone(SPEAKERPIN, 1000, 100);
            break;

        case 'r':
            tone(SPEAKERPIN, 10000, 100);
            break;

        case 'b':
            tone(SPEAKERPIN, 4000, 100);
            break;

        case 'w':
        {
            String str = Serial.readStringUntil('\n');

            rewardsize = str.toInt();

            reportRewardSize();
            break;
        }

        case 'g':
        {
            giveReward();

            reportReward();
            break;
        }

        case 'z': // Start "zap" protocol for laser stim
        {
            rampingDown = false;
            analogWrite(LASERPIN, 255);
            break;
        }

        case 'x': // Hardcutoff to laser stim
        {
            rampingDown = false;
            analogWrite(LASERPIN, 0);
            break;
        }

        case 'c': // Slow rampdown to laser stim
        {
            String str = Serial.readStringUntil('\n');

            rampDurationUs = max(1UL, str.toInt() * 1000UL);
            rampStartUs = micros();
            rampStartPWM = 255;
            pwm_last = -1;

            rampingDown = true;

            break;
        }

        case 'l': // Lock the wheel
        {
            wheelLock.write(60);
            break;
        }

        case 'u': // Unlock the wheel
        {
            wheelLock.write(90);
            break;
        }

        case 'a': // Set to specific angle
        {
            String str = Serial.readStringUntil('\n');

            angle = str.toInt();
            wheelLock.write(angle);
            break;
        }

        case 't':
        {
            reportTime();
            break;
        }

        case 'e':
        {
            reportRewardError();
            break;
        }

        case 'f':
        {
            measureLoopRequested = true;

            loopCounter = 0;
            loopCounterStart = millis();

            break;
        }

        case 'o':   // camera ON
        {
            camOnline = true;
            break;
        }

        case 'k':   // camera OFF
        {
            camOnline = false;
            break;
        }

        case 'B': // debug modes
        {
            String str = Serial.readStringUntil('\n');

            code = str.toInt();
            if (code == 0)
            {
                suppressLickReports = false;
                suppressRotaryReports = false;
                suppressCommandReports = false;
            }
            else if (code == 1)
            {
                suppressLickReports = true;
            }
            else if (code == 2)
            {
                suppressRotaryReports = true;
            }
            else if (code == 3)
            {
                suppressCommandReports = true;
            }
                
        }
    }
}

void handleSerial()
{
    while (Serial.available())
    {
        char cmd = (char)Serial.read();
        executeCommand(cmd);
    }
}

// -----------------------------------------------------------------------------
// Scheduled Tasks
// -----------------------------------------------------------------------------

Task lickTask(
    LICK_PERIOD_MS,
    TASK_FOREVER,
    &reportLick
);

Task rotaryTask(
    ROTARY_PERIOD_MS,
    TASK_FOREVER,
    &reportRotary
);

Task camTask(
    CAM_PULSE_PERIOD_MS,
    TASK_FOREVER,
    &triggerCameraPulse
);

// -----------------------------------------------------------------------------
// Setup
// -----------------------------------------------------------------------------

void setup()
{
    Serial.begin(115200);

    pinMode(LED_BUILTIN, OUTPUT);

    pinMode(SPEAKERPIN, OUTPUT);

    pinMode(CAM_PIN, OUTPUT);
    digitalWrite(CAM_PIN, LOW);

    pinMode(LASERPIN, OUTPUT);
    analogWrite(LASERPIN, 0);

    pinMode(REWARDPIN, OUTPUT);
    digitalWrite(REWARDPIN, LOW);

    pinMode(MANUALREWARDPIN, INPUT_PULLUP);

    pinMode(LICKOMETERDIGPIN, INPUT);
    pinMode(LICKOMETERANALOGPIN, INPUT);

    wheelLock.attach(SERVOMOTORPIN);
    wheelLock.write(90);

    runner.init();

    runner.addTask(lickTask);
    runner.addTask(rotaryTask);
    runner.addTask(camTask);

    lickTask.enable();
    rotaryTask.enable();
    camTask.enable();
}

// -----------------------------------------------------------------------------
// Main Loop
// -----------------------------------------------------------------------------

void loop()
{
    // -------------------------------------------------------------
    // Post-report pause
    // -------------------------------------------------------------

    if (pauseAfterReport)
    {
        if ((millis() - pauseStart) >= 5000)
        {
            pauseAfterReport = false;
        }

        return;
    }

    // -------------------------------------------------------------
    // Normal operation
    // -------------------------------------------------------------

    handleSerial();

    checkManualReward();

    checkReward();

    runner.execute();

    // -------------------------------------------------------------
    // Loop frequency measurement
    // -------------------------------------------------------------

    if (measureLoopRequested)
    {
        loopCounter++;

        if ((millis() - loopCounterStart) >= 1000)
        {
            reportLoopHz(loopCounter);

            measureLoopRequested = false;

            pauseAfterReport = true;
            pauseStart = millis();
        }
    }

    // -------------------------------------------------------------
    // Laser rampdown
    // -------------------------------------------------------------
    if (rampingDown)
    {
        uint32_t elapsed = micros() - rampStartUs;

        if (elapsed >= rampDurationUs)
        {
            analogWrite(LASERPIN, 0);
            rampingDown = false;
        }
        else
        {
            int pwm =
                rampStartPWM -
                ((long)rampStartPWM * elapsed) / rampDurationUs;
            if (pwm != pwm_last)
            {
                analogWrite(LASERPIN, pwm);
                pwm_last = pwm;
            }

        }
    }
    // -------------------------------------------------------------
    // End Camera Pulse
    // -------------------------------------------------------------
    if (camPulseActive)
    {
        if ((micros() - camPulseStart) >= CAM_PULSE_WIDTH_US)
        {
            digitalWrite(CAM_PIN, LOW);
            camPulseActive = false;
        }
    }
}